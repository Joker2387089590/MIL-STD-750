#include "reg52.h"

unsigned char state;
unsigned char buf[4];

void uart_init()
{
    SCON=0X50;			//设置为工作方式1
		TMOD=0X20;			//设置计数器工作方式2
		PCON=0X80;			//波特率加倍
		TH1=0XFA;				//计数器初始值设置，注意波特率是9600的
		TL1=0XFA;
		ES=1;						//打开接收中断
		EA=1;						//打开总中断
		TR1=1;					//打开计数器
    SBUF = 0x00;
}

void resetBuf()
{
    state = 0xFF;
    buf[0] = 0;
    buf[1] = 0;
    buf[2] = 0;
    buf[3] = 0;
}

void applyBuf()
{
    P0 = buf[0];
    P1 = buf[1];
    P2 = buf[2];
    P3 = buf[3];
}

unsigned char readByte()
{
	unsigned char sbuf;
  RI = 0; // 清除接收中断标志位
	
	sbuf = SBUF;
	switch(state)
	{
	case 0xFF:
			if(sbuf != 0xAA) break;
			state = 0;
			break;
	case 0:
	case 1:
	case 2:
	case 3:
			buf[state] = sbuf;
			SBUF = buf[state];
			state += 1;
			break;
	case 4:
			if(sbuf == 0x55) applyBuf();
	default:
			resetBuf();
			break;
	}
	return sbuf;
}

void writeByte(unsigned char sbuf)
{
	SBUF = sbuf;
	TI = 1;
}

void uart() interrupt 4 //串口通信中断函数
{
		unsigned char cache;
    if(TI) TI = 0; // 清除发送中断标志位
    if(RI)
    {
				cache = readByte(); // 处理接收到的数据
				writeByte(cache); // 回传数据
    }
}

void main()
{
    uart_init();
    resetBuf();
    while(1);
}

