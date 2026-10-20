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

add_library(yakuza_overlay src/overlay_slot.cpp)
target_compile_features(yakuza_overlay PUBLIC cxx_std_20)
target_include_directories(yakuza_overlay PUBLIC include)

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
    add_executable(overlay_slot_tests tests/test_overlay_slot.cpp)
    target_link_libraries(overlay_slot_tests PRIVATE yakuza_overlay)
    add_test(NAME overlay_slot COMMAND overlay_slot_tests)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_test(NAME preparation_formats
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v)
    set_tests_properties(preparation_formats PROPERTIES WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
endif()
