#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${repo_root}/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then
  python_bin="$(command -v python3)"
fi

applications_dir="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
mkdir -p "${applications_dir}"
cat > "${applications_dir}/usta.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=USTA
Comment=Screen region translation
Exec=${python_bin} ${repo_root}/run.py
Path=${repo_root}
Terminal=false
Categories=Utility;
EOF
chmod 644 "${applications_dir}/usta.desktop"

printf 'Installed USTA desktop entry: %s\n' "${applications_dir}/usta.desktop"
printf 'Exec: %s %s/run.py\n' "${python_bin}" "${repo_root}"
