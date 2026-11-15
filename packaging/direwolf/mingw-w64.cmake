# The cross-build of Direwolf for 64-bit Windows on Linux (scripts/build-direwolf --windows): the MinGW-w64 compilers of the build machine (Debian's gcc-mingw-w64-x86-64 and g++-mingw-w64-x86-64; Direwolf's
# project names no languages, so CMake enables C and C++ and keys its compiler checks on the C++ compiler), the resource compiler for the icon 1.8 embeds, and nothing of the Linux host looked for.
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER x86_64-w64-mingw32-gcc)
set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++)
set(CMAKE_RC_COMPILER x86_64-w64-mingw32-windres)
set(CMAKE_AR x86_64-w64-mingw32-ar)
set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
