# Cross-platform implementation checks

Python 39 files: syntax passed. Common custom imports and OS dispatch passed. Linux stable config ELF/SHA check passed without extraction/matching. SourceAFIS classpath checked using mocked subprocess: Linux colon, Windows semicolon.

Windows NBIS six mocked cases: normal, insufficient_features, process failure, timeout, malformed RAW stdout, malformed MATCH stdout. These are Python adapter tests, **not Windows runtime execution**. Native algorithm sections are identical; Windows changes are UTF-16 argv to UTF-8, Unicode file access and binary LF output.

Core transform AST is identical after normalizing the system temporary path. Linux NBIS job AST is also unchanged after that path normalization. Linux native source passed g++ syntax-only check; Linux shell setup passed bash -n.

MinGW cross compiler, CMake and PowerShell were unavailable. Windows C++ compile/link and PowerShell parser checks were not performed. No Windows EXE or runtime/JAR is included. Actual Windows build/fixture, shared transform failure contract and SourceAFIS execution remain necessary.

LINUX_PIPELINE_VALIDATED=true refers to the existing Linux development baseline. New-layout regression is static only. WINDOWS_IMPLEMENTATION_READY=true; WINDOWS_CROSS_BUILD_SUCCESS=false; WINDOWS_RUNTIME_VALIDATED=false; FINAL_INDEPENDENT_VALIDATION_COMPLETE=false; PROJECT_COMPLETE=false.
