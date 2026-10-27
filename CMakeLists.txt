cmake_minimum_required(VERSION 3.21)
project(YakuzaRecompResearch LANGUAGES CXX)

include(CTest)
include(FetchContent)

# Only the IOP component is needed by this diagnostic tool. No game code,
# graphics backend, Windows SDK-specific path or Linux service is required.
set(PS2X_IOP_BUILD_TESTS ${BUILD_TESTING} CACHE BOOL "Build upstream IOP tests" FORCE)
FetchContent_Declare(ps2recomp
    GIT_REPOSITORY https://github.com/ran-j/PS2Recomp.git
    GIT_TAG eb8688b2fd191129f103a39543002c005b33409c
    SOURCE_SUBDIR ps2xIOP
)
FetchContent_MakeAvailable(ps2recomp)

# Keep the pinned dependency intact; prepare only the required IOP implementations.
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
set(iop_private "${CMAKE_CURRENT_BINARY_DIR}/iop-private")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_iop.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_iop_idle.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_iop_rpc.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_iop.py"
    --iop-dir "${ps2recomp_SOURCE_DIR}/ps2xIOP" --out-dir "${iop_private}"
    COMMAND_ERROR_IS_FATAL ANY)
get_target_property(iop_sources ps2_iop SOURCES)
set(adapted_iop_sources)
set(iop_adaptation_count 0)
foreach(iop_source IN LISTS iop_sources)
    cmake_path(ABSOLUTE_PATH iop_source BASE_DIRECTORY "${ps2recomp_SOURCE_DIR}/ps2xIOP" OUTPUT_VARIABLE absolute_iop_source)
    cmake_path(RELATIVE_PATH absolute_iop_source BASE_DIRECTORY "${ps2recomp_SOURCE_DIR}/ps2xIOP" OUTPUT_VARIABLE relative_iop_source)
    if(NOT relative_iop_source MATCHES "^src/" OR NOT EXISTS "${iop_private}/${relative_iop_source}")
        message(FATAL_ERROR "Pinned IOP source has no coherent private compilation copy")
    endif()
    list(APPEND adapted_iop_sources "${iop_private}/${relative_iop_source}")
    math(EXPR iop_adaptation_count "${iop_adaptation_count}+1")
endforeach()
if(NOT iop_adaptation_count EQUAL 23)
    message(FATAL_ERROR "Pinned IOP emulator target source no longer matches")
endif()
set_property(TARGET ps2_iop PROPERTY SOURCES "${adapted_iop_sources}")
target_include_directories(ps2_iop PRIVATE
    "${iop_private}/src" "${iop_private}/src/emulator" "${iop_private}/src/emulator/core")
foreach(iop_test IN ITEMS ps2_iop_import_tests ps2_iop_import_version_tests)
    if(TARGET ${iop_test})
        target_include_directories(${iop_test} BEFORE PRIVATE "${iop_private}/src")
    endif()
endforeach()

add_library(yakuza_overlay src/overlay_slot.cpp)
target_compile_features(yakuza_overlay PUBLIC cxx_std_20)
target_include_directories(yakuza_overlay PUBLIC include)

add_library(yakuza_input src/native_pad.cpp)
target_compile_features(yakuza_input PUBLIC cxx_std_20)
target_include_directories(yakuza_input PUBLIC include)

add_library(yakuza_disc_ranges src/disc_ranges.cpp)
target_compile_features(yakuza_disc_ranges PUBLIC cxx_std_20)
target_include_directories(yakuza_disc_ranges PUBLIC include)

add_library(yakuza_ipu src/ipu_bitstream.cpp src/ipu_block.cpp)
target_compile_features(yakuza_ipu PUBLIC cxx_std_20)
target_include_directories(yakuza_ipu PUBLIC include)
add_library(yakuza_scratchpad_dma src/scratchpad_dma.cpp)
target_compile_features(yakuza_scratchpad_dma PUBLIC cxx_std_20)
target_include_directories(yakuza_scratchpad_dma PUBLIC include)

set(YAKUZA_OVERLAY_ANALYSIS_DIR "" CACHE PATH "Private, verified overlay analysis directory")
if(YAKUZA_OVERLAY_ANALYSIS_DIR)
    set(overlay_samples)
    foreach(module game health ufocatcher)
        if(module STREQUAL "game")
            set(sample_name "game_FUN_006426e0_0x6426e0.cpp")
        else()
            set(sample_name "${module}_${module}_first_code_0x62dd00.cpp")
        endif()
        set(sample "${YAKUZA_OVERLAY_ANALYSIS_DIR}/${module}/generated/${sample_name}")
        if(NOT EXISTS "${sample}")
            message(FATAL_ERROR "Run overlay_image.py analysis first; missing ${sample}")
        endif()
        list(APPEND overlay_samples "${sample}")
        set_property(SOURCE "${sample}" PROPERTY INCLUDE_DIRECTORIES "${YAKUZA_OVERLAY_ANALYSIS_DIR}/${module}/generated")
    endforeach()
    add_executable(yakuza_overlay_native_probe tools/overlay_native_probe.cpp ${overlay_samples})
    target_link_libraries(yakuza_overlay_native_probe PRIVATE yakuza_overlay ps2x::iop)
    target_include_directories(yakuza_overlay_native_probe PRIVATE
        "${ps2recomp_SOURCE_DIR}/ps2xRuntime/include"
        "${ps2recomp_SOURCE_DIR}/ps2xRuntime/src/lib/Kernel")
    if(NOT MSVC)
        target_compile_options(yakuza_overlay_native_probe PRIVATE -msse4.1)
    endif()
    if(WIN32)
        target_compile_definitions(yakuza_overlay_native_probe PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
        if(MINGW)
            target_link_options(yakuza_overlay_native_probe PRIVATE -municode)
        endif()
    endif()
endif()

add_executable(yakuza_iop_probe tools/iop_probe.cpp)
target_compile_features(yakuza_iop_probe PRIVATE cxx_std_20)
target_link_libraries(yakuza_iop_probe PRIVATE ps2x::iop)
if(WIN32)
    target_compile_definitions(yakuza_iop_probe PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    if(MINGW)
        target_link_options(yakuza_iop_probe PRIVATE -municode)
    endif()
endif()

if(BUILD_TESTING)
    set(mmi_private "${CMAKE_CURRENT_BINARY_DIR}/mmi-private")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mmi.py")
    execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mmi.py"
        --macros-header "${ps2recomp_SOURCE_DIR}/ps2xRuntime/include/ps2_runtime_macros.h"
        --out-file "${mmi_private}/ps2_runtime_macros.h"
        COMMAND_ERROR_IS_FATAL ANY)
    add_executable(mmi_permutation_tests tests/test_mmi_permutations.cpp)
    target_compile_features(mmi_permutation_tests PRIVATE cxx_std_20)
    target_include_directories(mmi_permutation_tests PRIVATE "${mmi_private}"
        "${ps2recomp_SOURCE_DIR}/ps2xRuntime/include" "${ps2recomp_SOURCE_DIR}/ps2xIOP/include")
    if(WIN32)
        target_compile_definitions(mmi_permutation_tests PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    endif()
    if(NOT MSVC)
        target_compile_options(mmi_permutation_tests PRIVATE -msse4.1)
    endif()
    add_test(NAME mmi_permutations COMMAND mmi_permutation_tests)
    add_executable(iop_interrupt_tests tests/test_iop_interrupts.cpp)
    target_link_libraries(iop_interrupt_tests PRIVATE ps2x::iop)
    target_include_directories(iop_interrupt_tests PRIVATE "${iop_private}/src/emulator")
    add_test(NAME iop_interrupts COMMAND iop_interrupt_tests)
    add_executable(overlay_slot_tests tests/test_overlay_slot.cpp)
    target_link_libraries(overlay_slot_tests PRIVATE yakuza_overlay)
    add_test(NAME overlay_slot COMMAND overlay_slot_tests)
    add_executable(native_pad_tests tests/test_native_pad.cpp)
    target_link_libraries(native_pad_tests PRIVATE yakuza_input)
    add_test(NAME native_pad COMMAND native_pad_tests)
    add_executable(disc_ranges_tests tests/test_disc_ranges.cpp)
    target_link_libraries(disc_ranges_tests PRIVATE yakuza_disc_ranges)
    add_test(NAME disc_ranges COMMAND disc_ranges_tests)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_test(NAME preparation_formats
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v)
    set_tests_properties(preparation_formats PROPERTIES WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
endif()

option(YAKUZA_BUILD_BOOT_PROBE "Build the full-runtime PAL boot development probe" OFF)
set(YAKUZA_MAIN_GENERATED_DIR "" CACHE PATH "Private resident/MAIN generated source directory")
if(YAKUZA_BUILD_BOOT_PROBE)
    include(cmake/boot-probe.cmake)
endif()
