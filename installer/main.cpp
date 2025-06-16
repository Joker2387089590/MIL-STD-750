#include <QCoreApplication>
#include <QProcess>
#include <QFile>
#include <QTemporaryDir>

int main(int argc, char *argv[])
{
	using namespace Qt::Literals;
	QCoreApplication a(argc, argv);

	QFile wheel(":/mil_std_750-1.1.0-py3-none-any.whl");
	wheel.open(QFile::ReadOnly);


	QTemporaryDir dir;
	{
		QFile output(dir.filePath("mil_std_750-1.1.0-py3-none-any.whl"));
		output.open(QFile::WriteOnly);
		output.write(wheel.readAll());
	}

	QProcess pip;
	pip.setProgram("python.exe");
	pip.setArguments(QProcess::splitCommand(u"-m pip install mil_std_750-1.1.0-py3-none-any.whl"));
	pip.setWorkingDirectory(dir.path());
	pip.setProcessChannelMode(QProcess::ForwardedChannels);
	pip.start();
	QObject::connect(&pip, &QProcess::finished, &a, [&pip, &a](int code, QProcess::ExitStatus status) {
		if(code == 0) qInfo() << "安全完成! 请运行 晶体管安全工作区测试平台.exe 确认安装成功";
	});
	return a.exec();
}
