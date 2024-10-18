socat -d -d pty,raw,echo=0 pty,raw,echo=0
socat -d -d pty,raw,echo=0 pty,raw,echo=0,ignoreeof,of=/dev/null

模拟器：
socat -d -d pty,raw,echo=0 pty,raw,echo=0,ignoreeof | stdbuf -o0 cat
cat /dev/ttys005
