# The default tools stay lightweight. This opt-in target builds the real upstream
# desktop runtime and the user's privately generated resident/MAIN translation.
if(NOT EXISTS "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
    message(FATAL_ERROR "Set YAKUZA_MAIN_GENERATED_DIR to verified resident/MAIN output")
endif()
set(PS2X_ENABLE_DEBUG_UI OFF CACHE BOOL "Boot probe has no optional debug UI" FORCE)
set(PS2X_ENABLE_AGRESSIVE_LOGS OFF CACHE BOOL "Bound logs during boot tracing" FORCE)
set(PS2X_ENABLE_IOP_RPC_TRACE ON CACHE BOOL "Keep missing RPC diagnostics" FORCE)
add_subdirectory("${ps2recomp_SOURCE_DIR}/ps2xRuntime" "${CMAKE_BINARY_DIR}/ps2-runtime" EXCLUDE_FROM_ALL)
target_link_libraries(ps2_runtime PRIVATE yakuza_ipu yakuza_scratchpad_dma)
option(YAKUZA_OPTIMIZE_BOOT_DEVICES "Optimize GCC/Clang runtime devices while retaining translated-code debug settings" ON)
if(YAKUZA_OPTIMIZE_BOOT_DEVICES AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang" AND NOT MSVC)
    foreach(native_target IN ITEMS ps2_runtime ps2_iop yakuza_ipu yakuza_scratchpad_dma)
        target_compile_options("${native_target}" PRIVATE -O2)
    endforeach()
endif()
target_sources(ps2_runtime PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/vu0_macro.cpp")
if(NOT MSVC)
    target_compile_options(ps2_runtime PUBLIC -msse4.1)
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
set(runtime_private "${CMAKE_CURRENT_BINARY_DIR}/runtime-private")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_runtime.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_vif.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_vif_irq.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_ipu.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_spr.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mmi.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/config/pal-runtime-layout.json")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_runtime.py"
    --runtime-dir "${ps2recomp_SOURCE_DIR}/ps2xRuntime" --out-dir "${runtime_private}"
    COMMAND_ERROR_IS_FATAL ANY)
get_target_property(runtime_sources ps2_runtime SOURCES)
set(adapted_sources)
foreach(source IN LISTS runtime_sources)
    cmake_path(ABSOLUTE_PATH source BASE_DIRECTORY "${ps2recomp_SOURCE_DIR}/ps2xRuntime" OUTPUT_VARIABLE absolute_source)
    cmake_path(IS_PREFIX ps2recomp_SOURCE_DIR "${absolute_source}" NORMALIZE in_dependency)
    if(in_dependency AND absolute_source MATCHES "/ps2xRuntime/src/lib/(.+)$")
        list(APPEND adapted_sources "${runtime_private}/src/lib/${CMAKE_MATCH_1}")
    else()
        list(APPEND adapted_sources "${source}")
    endif()
endforeach()
set_property(TARGET ps2_runtime PROPERTY SOURCES "${adapted_sources}")
target_include_directories(ps2_runtime BEFORE PUBLIC "${runtime_private}/include")
target_include_directories(ps2_runtime BEFORE PRIVATE
    "${runtime_private}/src/lib/Kernel" "${runtime_private}/src/lib")
set(boot_private "${CMAKE_CURRENT_BINARY_DIR}/boot-private")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_vu0.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/vu-macro/raw_vsub.cpp")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_vu0.py"
    --generated-dir "${YAKUZA_MAIN_GENERATED_DIR}" --out-dir "${boot_private}/vu0-corrections"
    COMMAND_ERROR_IS_FATAL ANY)
include("${boot_private}/vu0-corrections/vu0-corrections.cmake")
if(YAKUZA_VU0_INPUTS)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${YAKUZA_VU0_INPUTS})
endif()
set(YAKUZA_BOOT_SUPPLEMENT_DIR "" CACHE PATH "Private translation of newly decoded boot code")
set(supplement_args)
if(YAKUZA_BOOT_SUPPLEMENT_DIR)
    list(APPEND supplement_args --supplement-dir "${YAKUZA_BOOT_SUPPLEMENT_DIR}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${YAKUZA_BOOT_SUPPLEMENT_DIR}/register_functions.cpp")
endif()
file(MAKE_DIRECTORY "${boot_private}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_ipu_wait.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_ipu_wait.py"
    --generated-dir "${YAKUZA_MAIN_GENERATED_DIR}" --out-dir "${boot_private}"
    COMMAND_ERROR_IS_FATAL ANY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot.py"
    "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot.py"
    --generated-dir "${YAKUZA_MAIN_GENERATED_DIR}" --out-dir "${boot_private}"
    ${supplement_args}
    COMMAND_ERROR_IS_FATAL ANY)
set(YAKUZA_BOOT_OVERLAY_DIRS "" CACHE STRING "Private verified overlay analysis directories; separate with semicolons")
set(overlay_args)
foreach(folder IN LISTS YAKUZA_BOOT_OVERLAY_DIRS)
    list(APPEND overlay_args --module-dir "${folder}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${folder}/layout.json" "${folder}/verification.json" "${folder}/decoded.csv"
        "${folder}/generated/register_functions.cpp")
endforeach()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot_overlays.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/overlay_image.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot_overlays.py"
    --out-dir "${boot_private}" ${overlay_args} COMMAND_ERROR_IS_FATAL ANY)
include("${boot_private}/boot_overlays.cmake")
add_library(yakuza_boot_overlay_dispatch STATIC src/boot_overlays.cpp)
target_link_libraries(yakuza_boot_overlay_dispatch PUBLIC yakuza_overlay PRIVATE ps2_runtime)
file(GLOB boot_generated CONFIGURE_DEPENDS "${YAKUZA_MAIN_GENERATED_DIR}/*.cpp")
list(REMOVE_ITEM boot_generated "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
# Preserve source order so correcting a helper does not regroup later unity batches.
foreach(source replacement IN ZIP_LISTS YAKUZA_VU0_INPUTS YAKUZA_VU0_OUTPUTS)
    list(FIND boot_generated "${source}" position)
    if(position LESS 0)
        message(FATAL_ERROR "Verified VU0 source is absent from the boot target")
    endif()
    list(REMOVE_AT boot_generated ${position})
    list(INSERT boot_generated ${position} "${replacement}")
endforeach()
add_executable(yakuza_boot_probe tools/boot_probe.cpp src/pal_boot_hooks.cpp
    "${boot_private}/register_boot.cpp" "${boot_private}/boot_supplement.cpp"
    "${boot_private}/register_boot_overlays.cpp" ${boot_generated})
target_link_libraries(yakuza_boot_probe PRIVATE ps2_runtime yakuza_overlay yakuza_input yakuza_disc_ranges)
target_link_libraries(yakuza_boot_probe PRIVATE yakuza_boot_overlay_dispatch ${YAKUZA_BOOT_OVERLAY_TARGETS})
target_include_directories(yakuza_boot_probe PRIVATE "${YAKUZA_MAIN_GENERATED_DIR}")
# Per-source include keeps the translated-code PCH independent of native layout.
set_source_files_properties(tools/boot_probe.cpp src/pal_boot_hooks.cpp PROPERTIES
    INCLUDE_DIRECTORIES "${runtime_private}")
target_precompile_headers(yakuza_boot_probe PRIVATE
    "${runtime_private}/include/ps2_runtime_macros.h"
    "${YAKUZA_MAIN_GENERATED_DIR}/ps2_recompiled_functions.h"
    "${YAKUZA_MAIN_GENERATED_DIR}/ps2_recompiled_stubs.h")
set_target_properties(yakuza_boot_probe PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 32)
# Large generated registration functions and very large guest functions compile
# separately to keep compiler memory bounded.
set_source_files_properties("${boot_private}/register_boot.cpp" "${boot_private}/boot_supplement.cpp"
    "${boot_private}/register_boot_overlays.cpp"
    tools/boot_probe.cpp src/pal_boot_hooks.cpp
    PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)
set_source_files_properties("${boot_private}/boot_supplement.cpp" PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
set_source_files_properties("${boot_private}/register_boot_overlays.cpp" PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
if(YAKUZA_BOOT_SUPPLEMENT_DIR)
    file(GLOB supplement_sources CONFIGURE_DEPENDS "${YAKUZA_BOOT_SUPPLEMENT_DIR}/*.cpp")
    list(REMOVE_ITEM supplement_sources "${YAKUZA_BOOT_SUPPLEMENT_DIR}/register_functions.cpp")
    foreach(source IN LISTS supplement_sources)
        # Verified generated versions may share unchanged source files. Keep
        # each physical source and its own declarations stable across versions.
        get_filename_component(canonical_source "${source}" REALPATH)
        get_filename_component(source_include "${canonical_source}" DIRECTORY)
        target_sources(yakuza_boot_probe PRIVATE "${canonical_source}")
        set_source_files_properties("${canonical_source}" PROPERTIES
            SKIP_PRECOMPILE_HEADERS ON SKIP_UNITY_BUILD_INCLUSION ON
            INCLUDE_DIRECTORIES "${source_include}")
    endforeach()
endif()
foreach(source IN LISTS boot_generated)
    file(SIZE "${source}" source_size)
    if(source_size GREATER 524288)
        set_source_files_properties("${source}" PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)
    endif()
endforeach()
if(WIN32)
    target_compile_definitions(yakuza_boot_probe PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    # Translated Debug functions can consume nearly 1 MiB in one native frame.
    # Reserve a Linux-sized host stack; the emulated PS2 stack is unchanged.
    if(MINGW)
        target_link_options(yakuza_boot_probe PRIVATE -municode "-Wl,--stack,8388608")
    elseif(MSVC)
        target_link_options(yakuza_boot_probe PRIVATE "/STACK:8388608")
    endif()
endif()
if(BUILD_TESTING)
    # Exercise the exact copied header used by translated code in this build.
    target_include_directories(mmi_permutation_tests BEFORE PRIVATE "${runtime_private}/include")
    add_executable(boot_dispatch_tests tests/test_boot_dispatch.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_dispatch_tests PRIVATE ps2_runtime)
    target_include_directories(boot_dispatch_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_dispatch COMMAND boot_dispatch_tests)
    add_executable(boot_priority_tests tests/test_boot_priority.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_priority_tests PRIVATE ps2_runtime)
    target_include_directories(boot_priority_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_priority COMMAND boot_priority_tests)
    add_executable(boot_resume_tests tests/test_boot_resume.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_resume_tests PRIVATE ps2_runtime)
    target_include_directories(boot_resume_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_resume COMMAND boot_resume_tests)
    add_executable(boot_vif_tests tests/test_boot_vif.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_vif_tests PRIVATE ps2_runtime)
    target_include_directories(boot_vif_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_vif COMMAND boot_vif_tests)
    add_executable(boot_vu_flags_tests tests/test_boot_vu_flags.cpp
        "${YAKUZA_VU0_TEST_SOURCE}"
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_vu_flags_tests PRIVATE ps2_runtime)
    target_include_directories(boot_vu_flags_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host"
        "${CMAKE_CURRENT_SOURCE_DIR}/include")
    add_test(NAME boot_vu_flags COMMAND boot_vu_flags_tests)
    add_executable(boot_ipu_tests tests/test_boot_ipu.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_ipu_tests PRIVATE ps2_runtime)
    target_include_directories(boot_ipu_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_ipu COMMAND boot_ipu_tests)
    add_executable(boot_spr_tests tests/test_boot_spr.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_spr_tests PRIVATE ps2_runtime yakuza_scratchpad_dma)
    target_include_directories(boot_spr_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_spr COMMAND boot_spr_tests)
    add_executable(boot_overlay_tests tests/test_boot_overlays.cpp
        tests/fixtures/boot-host/register_functions.cpp tests/fixtures/boot-host/synthetic_entry.cpp)
    target_link_libraries(boot_overlay_tests PRIVATE yakuza_boot_overlay_dispatch ps2_runtime)
    target_include_directories(boot_overlay_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/boot-host")
    add_test(NAME boot_overlay COMMAND boot_overlay_tests)
    add_test(NAME boot_host_input_validation
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_boot_cli.py"
                "$<TARGET_FILE:yakuza_boot_probe>")
    if(WIN32 AND NOT CMAKE_CROSSCOMPILING)
        add_test(NAME boot_windows_launcher
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_windows_launcher.py"
                --exe "$<TARGET_FILE:yakuza_boot_probe>"
                --launcher "${CMAKE_CURRENT_SOURCE_DIR}/packaging/windows-native/Run-Yakuza.cmd")
    endif()
endif()
