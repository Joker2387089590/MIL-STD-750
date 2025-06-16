#include <string>
#include <fmt/xchar.h>
#include <Windows.h>

int APIENTRY WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nShowCmd)
{
	constexpr std::size_t size = MAX_PATH * 8;
	std::wstring pythonLocation;
	pythonLocation.resize(size);
	auto err = _wsearchenv_s(L"pythonw.exe", L"PATH", pythonLocation.data(), size);
	if(err != 0) return err;

	auto cmd = fmt::format(LR"("{}" -m mil_std_750)", std::wstring_view(pythonLocation.c_str()));

	STARTUPINFOW info = { sizeof(info) };
	PROCESS_INFORMATION processInfo {};
	auto err2 = CreateProcessW(NULL, cmd.data(), NULL, NULL, TRUE, 0, NULL, NULL, &info, &processInfo);
	if (err2 == 0) return -1;
	return 0;
}
