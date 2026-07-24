// Cross-platform helpers for the FeedForge Electron main process.
//
// Centralizes the differences between Windows and POSIX (Linux/macOS) so the
// rest of main.cjs can stay platform-agnostic: virtualenv layout, executable
// names, and the local stem-server launcher command.

const path = require("path");

const IS_WINDOWS = process.platform === "win32";
const IS_MACOS = process.platform === "darwin";
const IS_LINUX = process.platform === "linux";

// Python virtualenv interpreter path differs by platform:
//   Windows: <venv>/Scripts/python.exe
//   POSIX:   <venv>/bin/python
function venvPython(venvRoot) {
  return IS_WINDOWS
    ? path.join(venvRoot, "Scripts", "python.exe")
    : path.join(venvRoot, "bin", "python");
}

// Basename of the packaged PyInstaller converter executable.
function converterExecutableName() {
  return IS_WINDOWS ? "psarc2feedpak.exe" : "psarc2feedpak";
}

// Basename of the nvidia-smi tool used for GPU detection.
function nvidiaSmiName() {
  return IS_WINDOWS ? "nvidia-smi.exe" : "nvidia-smi";
}

// Candidate system Python interpreter names, in priority order.
function pythonProbeNames() {
  return IS_WINDOWS ? ["python.exe"] : ["python3", "python"];
}

// Returns the launcher script filename and the command used to run it for the
// local stem server. Windows uses PowerShell; POSIX uses bash.
function stemLauncher() {
  if (IS_WINDOWS) {
    return {
      scriptName: "start-demucs-server.ps1",
      command: "powershell.exe",
      buildArgs: (scriptPath) => ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath],
    };
  }
  return {
    scriptName: "start-demucs-server.sh",
    command: "bash",
    buildArgs: (scriptPath) => [scriptPath],
  };
}

module.exports = {
  IS_WINDOWS,
  IS_MACOS,
  IS_LINUX,
  venvPython,
  converterExecutableName,
  nvidiaSmiName,
  pythonProbeNames,
  stemLauncher,
};
