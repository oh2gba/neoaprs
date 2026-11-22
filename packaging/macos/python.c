/* bin/python3.13 of the macOS app when the archive's own interpreter has all of Python linked into
 * it: the app already carries Python as lib/libpython3.13.dylib (the launcher embeds it), so this
 * program is the interpreter on that library instead, and the bundle holds Python once. It is
 * Python's own `main`, nothing more; at its place in bin/ Python finds the same prefix
 * (Contents/Resources) as the archive's interpreter did. scripts/build-macos-app builds it only
 * when `otool -L` of the archive's interpreter names no libpython. */
#include <Python.h>

int main(int argc, char **argv)
{
    return Py_BytesMain(argc, argv);
}
