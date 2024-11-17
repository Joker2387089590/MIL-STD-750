cmake_minimum_required(VERSION 3.28)
project(MIL-STD-750)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(fmt CONFIG REQUIRED)
find_package(Python 3.12 REQUIRED COMPONENTS Development Interpreter)

set(PYBIND11_FINDPYTHON ON CACHE BOOL "force pybind11 cmake_policy new" FORCE)
set_target_properties(Python::Python PROPERTIES MAP_IMPORTED_CONFIG_DEBUG ";RELEASE")
set_target_properties(Python::Module PROPERTIES MAP_IMPORTED_CONFIG_DEBUG ";RELEASE")
add_subdirectory(${CMAKE_SOURCE_DIR}/pybind11)

add_executable(launcher
    main.cpp
)

target_link_libraries(launcher 
    PRIVATE
        pybind11::embed
        fmt::fmt-header-only
)
