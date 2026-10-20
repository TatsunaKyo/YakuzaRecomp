# The default tools stay lightweight. This opt-in target builds the real upstream
# desktop runtime and the user's privately generated resident/MAIN translation.
if(NOT EXISTS "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
    message(FATAL_ERROR "Set YAKUZA_MAIN_GENERATED_DIR to verified resident/MAIN output")
endif()
set(PS2X_ENABLE_DEBUG_UI OFF CACHE BOOL "Boot probe has no optional debug UI" FORCE)
set(PS2X_ENABLE_AGRESSIVE_LOGS OFF CACHE BOOL "Bound logs during boot tracing" FORCE)
set(PS2X_ENABLE_IOP_RPC_TRACE ON CACHE BOOL "Keep missing RPC diagnostics" FORCE)
add_subdirectory("${ps2recomp_SOURCE_DIR}/ps2xRuntime" "${CMAKE_BINARY_DIR}/ps2-runtime" EXCLUDE_FROM_ALL)
if(NOT MSVC)
    target_compile_options(ps2_runtime PUBLIC -msse4.1)
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
set(boot_private "${CMAKE_CURRENT_BINARY_DIR}/boot-private")
set(YAKUZA_BOOT_SUPPLEMENT_DIR "" CACHE PATH "Private translation of newly decoded boot code")
set(supplement_args)
if(YAKUZA_BOOT_SUPPLEMENT_DIR)
    list(APPEND supplement_args --supplement-dir "${YAKUZA_BOOT_SUPPLEMENT_DIR}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${YAKUZA_BOOT_SUPPLEMENT_DIR}/register_functions.cpp")
endif()
file(MAKE_DIRECTORY "${boot_private}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot.py"
    "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_boot.py"
    --generated-dir "${YAKUZA_MAIN_GENERATED_DIR}" --out-dir "${boot_private}"
    ${supplement_args}
    COMMAND_ERROR_IS_FATAL ANY)
file(GLOB boot_generated CONFIGURE_DEPENDS "${YAKUZA_MAIN_GENERATED_DIR}/*.cpp")
list(REMOVE_ITEM boot_generated "${YAKUZA_MAIN_GENERATED_DIR}/register_functions.cpp")
add_executable(yakuza_boot_probe tools/boot_probe.cpp src/pal_boot_hooks.cpp
    "${boot_private}/register_boot.cpp" "${boot_private}/boot_supplement.cpp" ${boot_generated})
target_link_libraries(yakuza_boot_probe PRIVATE ps2_runtime yakuza_overlay)
target_include_directories(yakuza_boot_probe PRIVATE "${YAKUZA_MAIN_GENERATED_DIR}")
target_precompile_headers(yakuza_boot_probe PRIVATE
    "${ps2recomp_SOURCE_DIR}/ps2xRuntime/include/ps2_runtime_macros.h"
    "${YAKUZA_MAIN_GENERATED_DIR}/ps2_recompiled_functions.h"
    "${YAKUZA_MAIN_GENERATED_DIR}/ps2_recompiled_stubs.h")
set_target_properties(yakuza_boot_probe PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 32)
# Large generated registration functions and very large guest functions compile
# separately to keep compiler memory bounded.
set_source_files_properties("${boot_private}/register_boot.cpp" "${boot_private}/boot_supplement.cpp"
    tools/boot_probe.cpp src/pal_boot_hooks.cpp
    PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)
set_source_files_properties("${boot_private}/boot_supplement.cpp" PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
if(YAKUZA_BOOT_SUPPLEMENT_DIR)
    file(GLOB supplement_sources CONFIGURE_DEPENDS "${YAKUZA_BOOT_SUPPLEMENT_DIR}/*.cpp")
    list(REMOVE_ITEM supplement_sources "${YAKUZA_BOOT_SUPPLEMENT_DIR}/register_functions.cpp")
    target_sources(yakuza_boot_probe PRIVATE ${supplement_sources})
    set_source_files_properties(${supplement_sources} PROPERTIES
        SKIP_PRECOMPILE_HEADERS ON SKIP_UNITY_BUILD_INCLUSION ON
        INCLUDE_DIRECTORIES "${YAKUZA_BOOT_SUPPLEMENT_DIR}")
endif()
foreach(source IN LISTS boot_generated)
    file(SIZE "${source}" source_size)
    if(source_size GREATER 524288)
        set_source_files_properties("${source}" PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)
    endif()
endforeach()
if(WIN32)
    target_compile_definitions(yakuza_boot_probe PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    if(MINGW)
        target_link_options(yakuza_boot_probe PRIVATE -municode)
    endif()
endif()
if(BUILD_TESTING)
    add_test(NAME boot_host_input_validation
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_boot_cli.py"
                "$<TARGET_FILE:yakuza_boot_probe>")
endif()
