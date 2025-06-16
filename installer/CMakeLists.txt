cmake_minimum_required(VERSION 3.16)
project(mil_package LANGUAGES CXX)

set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Core)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Core)
find_package(fmt CONFIG REQUIRED)

add_executable(launcher WIN32
    launcher.cpp
    icon.rc
)

target_link_libraries(launcher PRIVATE
    fmt::fmt-header-only
)

set_target_properties(launcher PROPERTIES
    RUNTIME_OUTPUT_NAME "晶体管安全工作区测试平台"
)

add_executable(mil_package
    main.cpp
)

target_link_libraries(mil_package Qt${QT_VERSION_MAJOR}::Core)

set_target_properties(mil_package PROPERTIES
    RUNTIME_OUTPUT_NAME "晶体管安全工作区测试平台-安装包"
)

set(dist_dir "${PROJECT_SOURCE_DIR}/../dist")
cmake_path(NORMAL_PATH dist_dir)

qt_add_resources(mil_package dist
    PREFIX /
    BASE ${dist_dir}
    FILES
        ${dist_dir}/mil_std_750-1.1.0.tar.gz
        ${dist_dir}/mil_std_750-1.1.0-py3-none-any.whl
)

include(GNUInstallDirs)
install(TARGETS mil_package launcher
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
