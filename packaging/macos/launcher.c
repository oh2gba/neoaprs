/* The entry of the macOS app, NeoAPRS.app/Contents/MacOS/NeoAPRS: Python embedded through libpython, so that the process is NeoAPRS itself. The Dock, the menu bar and the microphone prompt name the
   process's own bundle and read its Info.plist, which they would not do for a python3.13 started by a script (the app would be "python3.13" with the generic icon). It runs `-m neoaprs` with the arguments
   it was given, and `app` with none, as the AppImage's AppRun does: NeoAPRS.app/Contents/MacOS/NeoAPRS is the desktop app from Finder and the `neoaprs` command from a terminal.

   The Python is the one laid out as Contents/Resources (bin/, lib/, tools/), which is told as the home; sys.executable is its bin/python3.13, so that what NeoAPRS starts with it (the daemon of the app,
   the launchd agent of `service install`) is a plain Python with the same prefix. The configuration is the isolated one of `python -I`: nothing of the user's environment or site, nothing of the current
   folder on sys.path; and no bytecode is written, because the bundle's signature seals its files (the build compiles every module in advance).

   Built by scripts/build-macos-app:  cc -O2 -mmacosx-version-min=14.0 -o Contents/MacOS/NeoAPRS launcher.c -I<Resources>/include/python3.13 -L<Resources>/lib -lpython3.13 -Wl,-rpath,@executable_path/../Resources/lib
   tests/test_macos_app.py builds and runs it on Linux against the venv's Python with a made-up Resources folder: the same code, the executable found through /proc instead of dyld. */
#include <Python.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#else
#include <unistd.h>
#endif

#define PYTHON "bin/python3.13"

/* The real path of this program, PATH_MAX long. */
static int executable_path(char *out) {
#ifdef __APPLE__
    char raw[PATH_MAX];
    uint32_t size = sizeof raw;
    if (_NSGetExecutablePath(raw, &size) != 0) return -1;
    return realpath(raw, out) == NULL ? -1 : 0;
#else
    ssize_t n = readlink("/proc/self/exe", out, PATH_MAX - 1);
    if (n < 0) return -1;
    out[n] = 0;
    return 0;
#endif
}

static void parent(char *path) {
    char *slash = strrchr(path, '/');
    if (slash != NULL) *slash = 0;
}

static int stopped(PyStatus status) {
    if (!PyStatus_Exception(status)) return 0;
    if (PyStatus_IsExit(status)) exit(status.exitcode);
    Py_ExitStatusException(status);
    return 1;
}

int main(int argc, char **argv) {
    char exe[PATH_MAX], resources[PATH_MAX + 16], python[PATH_MAX + 32];
    if (executable_path(exe) != 0) {
        perror("NeoAPRS: the path of the program could not be read");
        return 1;
    }
    strcpy(resources, exe);
    parent(resources);                       /* Contents/MacOS */
    parent(resources);                       /* Contents */
    strcat(resources, "/Resources");
    snprintf(python, sizeof python, "%s/%s", resources, PYTHON);

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.parse_argv = 1;                   /* -m is read from the arguments below */
    config.write_bytecode = 0;
    config.install_signal_handlers = 1;      /* Ctrl-C is a KeyboardInterrupt, as in a plain python */
    config.configure_c_stdio = 1;
    stopped(PyConfig_SetBytesString(&config, &config.home, resources));
    stopped(PyConfig_SetBytesString(&config, &config.executable, python));

    char **args = malloc(sizeof(char *) * (size_t) (argc + 4));
    int n = 0;
    args[n++] = argv[0];
    args[n++] = "-m";
    args[n++] = "neoaprs";
    if (argc > 1) {
        for (int i = 1; i < argc; i++) args[n++] = argv[i];
    } else {
        args[n++] = "app";
    }
    stopped(PyConfig_SetBytesArgv(&config, n, args));
    PyStatus status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    free(args);
    stopped(status);
    return Py_RunMain();
}
