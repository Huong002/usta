"""Single-owner capture loop with immutable translation jobs."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from usta.application.results import CaptureRequest, PerformanceTimings, TranslationRequest
from usta.application.settings import AppSettings
from usta.config import get_language_code
from usta.core.exceptions import PortalCanceledError, ScreenCaptureError
from usta.core.ocr.ocr_manager import OCRManager
from usta.core.translation.translator_manager import TranslatorManager

logger = logging.getLogger(__name__)


class Pipeline:
    LOOP_SLEEP_SECONDS = 0.2

    def __init__(
        self,
        *,
        capture_factory,
        publisher,
        image_path,
        on_translation,
        on_error,
        ocr_factory=OCRManager,
        translator_factory=TranslatorManager,
        rect_factory=tuple,
        preprocess=None,
        on_performance=lambda value: None,
        on_timings=lambda value: None,
        on_translating=lambda value: None,
        on_request_busy=lambda value: None,
    ):
        self.capture_factory = capture_factory
        self.publisher = publisher
        self.image_path = image_path
        self.on_translation = on_translation
        self.on_error = on_error
        self.ocr_factory = ocr_factory
        self.translator_factory = translator_factory
        self.rect_factory = rect_factory
        self.preprocess = preprocess
        self.on_performance = on_performance
        self.on_timings = on_timings
        self.on_translating = on_translating
        self.on_request_busy = on_request_busy
        self._settings = AppSettings()
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._stopped.set()
        self._session = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="usta-translation")
        self._future = None
        self._job = None
        self._job_started = None
        self._job_ocr_seconds = None
        self._job_one_shot = False
        self._one_shot_request = None
        self._one_shot_active = False
        self._one_shot_session = None
        self._request_ready = threading.Event()

    @property
    def session_id(self):
        with self._lock:
            return self._session

    @property
    def is_stopped(self):
        return self._stopped.is_set()

    def is_current(self, session):
        with self._lock:
            return not self._stopped.is_set() and self._session == session

    @property
    def settings(self):
        with self._lock:
            return deepcopy(self._settings)

    def configure(self, settings: AppSettings) -> None:
        with self._lock:
            self._settings = deepcopy(settings)
            self._session += 1

    @property
    def one_shot_busy(self):
        with self._lock:
            return self._one_shot_active or self._future is not None

    def request_once(self, capture_rect, dpi_scale) -> bool:
        with self._lock:
            if (
                self._stopped.is_set()
                or self._settings.capture_mode != "on_demand"
                or self._one_shot_active
                or self._future is not None
            ):
                return False
            request = CaptureRequest(tuple(capture_rect), dpi_scale, self._session)
            self._one_shot_request = request
            self._one_shot_active = True
            self._one_shot_session = request.session_id
            self._request_ready.set()
        self.on_request_busy(True)
        return True

    def _take_one_shot_request(self):
        with self._lock:
            request = self._one_shot_request
            self._one_shot_request = None
            if request is None:
                self._request_ready.clear()
            return request

    def _finish_one_shot(self, session):
        with self._lock:
            if not self._one_shot_active or self._one_shot_session != session:
                return
            self._one_shot_active = False
            self._one_shot_session = None
            if self._one_shot_request is not None and self._one_shot_request.session_id == session:
                self._one_shot_request = None
            self._request_ready.clear()
        self.on_request_busy(False)

    def start(self) -> None:
        with self._lock:
            self._session += 1
            self._stopped.clear()

    def stop(self) -> None:
        with self._lock:
            self._session += 1
            self._stopped.set()
            was_busy = self._one_shot_active
            self._one_shot_request = None
            self._one_shot_active = False
            self._one_shot_session = None
            self._request_ready.clear()
        if was_busy:
            self.on_request_busy(False)

    def close(self) -> None:
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _translate(self, request, keys):
        # This manager is used only by the translation owner thread, never by UI.
        translation_started = time.perf_counter()
        translator = self.translator_factory()
        for name, key in keys.items():
            translator.set_api_key(name, key)
        result = translator.translate_request(request)
        completed = time.perf_counter()
        return result, completed, completed - translation_started

    def _collect(self):
        if self._future is None or not self._future.done():
            return
        future, job, started = self._future, self._job, self._job_started
        ocr_seconds = self._job_ocr_seconds
        one_shot = self._job_one_shot
        self._future = self._job = self._job_started = self._job_ocr_seconds = None
        self._job_one_shot = False
        with self._lock:
            valid = not self._stopped.is_set() and job.session_id == self._session
            if not valid:
                self.on_translating(False)
                if one_shot:
                    self._finish_one_shot(job.session_id)
                return
            self.on_translating(False)
            try:
                result, completed, translation_seconds = future.result()
            except Exception as exc:
                self.on_error(str(exc))
                if one_shot:
                    self._finish_one_shot(job.session_id)
                return
            self.on_translation(result.translated_text)
            self.publisher.broadcast(
                original=job.text,
                translated=result.translated_text,
                source_lang=job.source_lang,
                target_lang=job.target_lang,
                engine=job.engine_name,
            )
            self.on_timings(
                PerformanceTimings(ocr_seconds, translation_seconds, completed - started)
            )
            self.on_performance(completed - started)
            if one_shot:
                self._finish_one_shot(job.session_id)

    def _capture_once(self, capture, ocr, settings, session, request):
        started = time.perf_counter()
        if not capture.capture(
            self.rect_factory(request.capture_rect), self.image_path, request.dpi_scale
        ):
            return False

        ocr_started = time.perf_counter()
        if settings.ocr_engine == "Tesseract" and self.preprocess:
            self.preprocess(self.image_path, self.image_path)
        text = ocr.read_result(self.image_path).text
        ocr_seconds = time.perf_counter() - ocr_started
        if len(text) <= 2:
            return False

        translation = TranslationRequest(
            text,
            get_language_code(settings.source_lang, settings.source_lang),
            get_language_code(settings.target_lang, settings.target_lang),
            settings.translator_engine,
            session,
        )
        with self._lock:
            if (
                session != self._session
                or self._stopped.is_set()
                or settings.capture_mode != "on_demand"
                or self._future is not None
            ):
                return False
            self._job = translation
            self._job_started = started
            self._job_ocr_seconds = ocr_seconds
            self._job_one_shot = True
            self._future = self._executor.submit(
                self._translate, translation, settings.translator_api_keys
            )
            self.on_translating(True)
        return True

    def run(self) -> None:
        capture = None
        applied = -1
        capture_name = None
        last_text = ""
        ocr = self.ocr_factory()
        try:
            self.publisher.start()
            while not self._stopped.is_set():
                capture_request = None
                try:
                    with self._lock:
                        settings, session = deepcopy(self._settings), self._session
                    if session != applied:
                        if capture is None or capture_name != settings.screenshot_engine:
                            if capture is not None:
                                capture.close()
                            capture = self.capture_factory(settings.screenshot_engine)
                            capture_name = settings.screenshot_engine
                        ocr.set_engine(settings.ocr_engine)
                        ocr.set_language(
                            get_language_code(settings.source_lang, settings.source_lang)
                        )
                        applied = session
                        last_text = ""
                    self._collect()
                    if self._stopped.is_set():
                        break
                    if settings.capture_mode == "on_demand":
                        capture_request = self._take_one_shot_request()
                        if capture_request is None:
                            self._request_ready.wait(self.LOOP_SLEEP_SECONDS)
                            continue
                        if capture_request.session_id != session:
                            self._finish_one_shot(capture_request.session_id)
                            continue
                        if not self._capture_once(
                            capture, ocr, settings, session, capture_request
                        ):
                            self._finish_one_shot(capture_request.session_id)
                        continue
                    started = time.perf_counter()
                    if capture.capture(
                        self.rect_factory(settings.capture_rect),
                        self.image_path,
                        settings.dpi_scale,
                    ):
                        ocr_started = time.perf_counter()
                        if settings.ocr_engine == "Tesseract" and self.preprocess:
                            self.preprocess(self.image_path, self.image_path)
                        text = ocr.read_result(self.image_path).text
                        ocr_seconds = time.perf_counter() - ocr_started
                        with self._lock:
                            if (
                                session == self._session
                                and not self._stopped.is_set()
                                and len(text) > 2
                                and text != last_text
                                and self._future is None
                            ):
                                request = TranslationRequest(
                                    text,
                                    get_language_code(settings.source_lang, settings.source_lang),
                                    get_language_code(settings.target_lang, settings.target_lang),
                                    settings.translator_engine,
                                    session,
                                )
                                self._job = request
                                self._job_started = started
                                self._job_ocr_seconds = ocr_seconds
                                self._job_one_shot = False
                                self._future = self._executor.submit(
                                    self._translate, request, settings.translator_api_keys
                                )
                                last_text = text
                                self.on_translating(True)
                except ScreenCaptureError as exc:
                    if capture_request is not None:
                        self._finish_one_shot(capture_request.session_id)
                    self.stop()
                    self.on_error(str(exc))
                except PortalCanceledError:
                    if capture_request is not None:
                        self._finish_one_shot(capture_request.session_id)
                    self.stop()
                except Exception as exc:
                    if capture_request is not None:
                        self._finish_one_shot(capture_request.session_id)
                    logger.exception("Capture/OCR pipeline failed")
                    self.on_error(str(exc))
                self._stopped.wait(self.LOOP_SLEEP_SECONDS)
        except Exception as exc:
            self.on_error(str(exc))
        finally:
            try:
                if capture is not None:
                    capture.close()
            finally:
                self.publisher.stop()
                self.on_translating(False)
