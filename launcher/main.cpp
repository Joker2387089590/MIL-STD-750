#include <pybind11/embed.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <fmt/format.h>

namespace py = pybind11;
using namespace std::literals;

int main()
{
    py::scoped_interpreter scope{};
    try {
        auto sys = py::module::import("sys");
        sys.attr("path").attr("append")(R"(C:\workspace\Repo\MIL-STD-750)"sv);

        auto main = py::module::import("src.main");
        return main.attr("main")().cast<int>();
    }
    catch(const std::exception& e)
    {
        fmt::println(stderr, "exception: {}", e.what());
        return -1;
    }
}
