#!/usr/bin/env python3

# TODO: webcam "polaroid"
# TODO: barcode + scanner oscillator (infinite trollface)

import subprocess
import signal
from PIL import Image,ImageEnhance,ImageFilter
import numpy as np
import sys
import os
import getopt
from time import sleep

MAX_WIDTH = 384
LF = 10   # 0A
CR = 13   # 0D
HT = 9    # 09
FF = 12   # 0C
ESC = 27  # 1B
FS = 28   # 1C
GS = 29   # 1D
DC2 = 18  # 12

TMP_PGM = 'thermal-printer-temp.pgm'


def sighandler(sig, frame):
    signal.signal(sig, signal.SIG_IGN)
    # kill the process group:
    os.kill(0, sig)
    print('Bye!')
    raise KeyboardInterrupt


def barcode(data):
    code = {
    'UPC-A': 0,  # 11 <= k/n <= 12; d: [0-9] (digits)
    'UPC-E': 1,  # 11 <= k/n <= 12; d: [0-9]
    'JAN13': 2,  # 12 <= k/n <= 13; d: [0-9]
    'JAN8': 3,   # 7 <= k/n <= 8; d: [0-9]
    'CODE39': 4, # 1 <= k'; 1 <= n <= 255; d: [0-9A-Z $%+-./]
    'ITF': 5,    # 1 <= k(even); 1 <= n <= 255(even); d: [0-9]
    'CODABAR': 6,  # 1 <= k'; 1 <= n <= 255; d: [0-9A-D$+-./:]
    'CODE93': 72,   # 1 <= n <= 255; d: [0x00-0x7f] (HRI characters?)
    'CODE128': 73   # 2 <= n <= 255; d: [0x00-0x7f] (U,A-Z,A,B,C,D,E,T)
    }
    NUL = 0
    MODE_B = 65
    data = data.split( )
    sys.stderr.write(f'{data}\n')
    sys.stdout.buffer.write(bytes([ESC,ord('@')]))  # Initialize printer
    sys.stdout.buffer.write(bytes([GS,ord('h'),80]))  # barcode height = 80
    sys.stdout.buffer.write(bytes([GS,ord('w'),3]))   # barcode width = 3
    #sys.stdout.buffer.write(bytes([GS,ord('H'),2]))   # data below barcode
    # A: GS k m [d]k NUL     0 <= m <= 6:   e.g. UPC-A
    # B: GS k m n [d]k       65 <= m <= 74: e.g. MODE_B+UPC-A
    sys.stdout.buffer.write(bytes([GS,ord('k'),code[data[0]]]))
    sys.stdout.buffer.write(bytes(data[1],'utf-8'))
    sys.stdout.buffer.write(bytes([0]))
    sys.stdout.buffer.write(bytes([LF]))


def image(img):
    # MSB Bitmap: DC2 "V" nL nH d1 ... d48
    # e.g. first 8 dots in a .pgm image: 0xCC 0x88 0x33 0x00 0x00 ...  ▓▒░  ...
    # will be 0b11000000 in MSB mode
    im = Image.open(img)
    
    heightChunk = 1
    nH = heightChunk // 256
    nL = heightChunk % 256

    p = np.array(im)
    row = 0
    line = [DC2,ord('V'),nL,nH]
    while row < im.height:
        byteWin = 0
        while byteWin < MAX_WIDTH:
            B = 0
            for i in range(8):
                if p[row][byteWin:byteWin+8][i] < 0x7F: B += 1
                B <<= 1 if (i < 7) else 0
            # In the model I'm using, if some byte==10, it will _blindly_ interpret it as a line feed
            if B==10: B=11
            line.append(B)
            byteWin += 8
        row += 1
        if(row % heightChunk == 0):
            sys.stdout.buffer.write(bytes(line))
            sys.stdout.flush()
            line = [DC2,ord('V'),nL,nH]
        

# Experimental
def sine():
    from scipy import interpolate
    import numpy as np
    dotsW = MAX_WIDTH
    interpY = 1000
    X = np.linspace(0,2*np.pi,100)
    Y = np.sin(X)*dotsW/2 + dotsW/2
    F = interpolate.interp1d(X,Y)
    X = np.linspace(0,2*np.pi,interpY)
    Y = F(X)
    
    data = []
    for y in Y.astype(int):
        B = [0]*(dotsW//8)
        index = y // 8  # 384 printer dots, 48 bytes. 383//8=47, the last byte
        B[index] = 128 >> (y % 8)
        data.extend(B[:])
    
    # For constructing images, format '1' is 8-pixels per byte, not 1 per byte as it says in the docs
    # The image is stored in 1-pixel per byte, and range {0,255}, and (as far as I know)
    # you can't go back to actual 8-pixels per byte
    im = Image.frombytes('1',(dotsW,interpY),bytes(data))
    
    # (Maybe I should use matplotlib to temp file instead)
    bytesPerRow = 48
    heightChunk = 256 // bytesPerRow  # 256 byte buffer (without dtr)
    imHeight = heightChunk * 40
    im = im.convert('RGB')
    im = im.resize((dotsW*2,interpY),Image.BILINEAR)
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    enhancer = ImageEnhance.Brightness(im)
    im = enhancer.enhance(200)

    # Now we need to resample and go back to 8-pixels per byte
    im = im.resize((MAX_WIDTH,imHeight),Image.BILINEAR)
    im = im.convert('1')
    im.save('thermal-printer-sine.bmp')
    p = np.array(im.getdata()).reshape(imHeight,MAX_WIDTH)

    # [DC2,ord('V'),nL,nH]: MSB bitmap
    # FIXME: "MSB bitmap" is slow.. even in big chunks?
    # [DC2,ord('*'),heightChunk,bytesPerRow]: same
    # [GS,ord('*'),imHeight,bytesPerRow]  # load bitmap... something is wrong with the documentation

    nH = imHeight // 256
    nL = imHeight % 256
    row = 0
    line = [DC2,ord('V'),nL,nH]
    while row < imHeight:
        byteWin = 0
        while byteWin < MAX_WIDTH:
            B = 0
            for i in range(8):
                if p[row][byteWin:byteWin+8][i] >= 0x7F: B += 1
                B <<= 1 if (i < 7) else 0
            if B==10: B=11
            line.append(B)
            byteWin += 8
        row += 1
        if(row % imHeight == 0):
            sys.stdout.buffer.write(bytes(line))
            sys.stdout.flush()
            line = [DC2,ord('V'),nL,nH]


def plot(minY,maxY,values,cnt,samples,text):
    import matplotlib.pyplot as plt
    from scipy import signal
    import numpy as np

    X = np.linspace(0,100,cnt)
    Y = np.asarray(values)

    # 0.3Hz high pass filter
    #sos = signal.butter(10,0.3,'hp',fs=cnt,output='sos')
    #filtered = signal.sosfilt(sos,Y)
    # FIXME: the step from 0 to each first sample causes the filtered samples
    #        to have discontinuity between each printed interval
    maxY = max(maxY,max(Y))
    minY = min(minY,min(Y)) 
    sys.stderr.write(f'\nSamples:{samples}, minY:{minY}, maxY:{maxY}, Values:{values[0:10]}...\n')

    fig, ax = plt.subplots()
    ax.plot(X,Y,'k-',linewidth=2.0)
    ax.set_ylim([minY,maxY])
    plt.axis('off')
    plt.margins(0,0)
    plt.savefig(f'temp.jpg',bbox_inches='tight',pad_inches=0)
    
    # `time head -n 200 samples.txt | ./thermal-printer.py -p` with a limit of 400 samples took about 10s
    # using a image height of 160. So, we have roughly 40 printed samples per second
    ptpY = np.ptp(Y)
    sys.stderr.write(f'peak-to-peak(Y): {ptpY}\n')
    if ptpY < 3000: text = ''
    subprocess.run(['convert','-gravity','North','-pointsize','40','-stretch','UltraExpanded',
        '-annotate','+0+0',text[33:50],
        '-rotate','90','-resize',f'{MAX_WIDTH}x160!','-monochrome','temp.jpg',TMP_PGM],check=True)
    image(TMP_PGM)


# min and max should be supplied
def parse(args,fs):
    min,max = args.split( )
    cnt = 0  # using a buffer of 100 samples
    values = []
    smps = 0
    text = ''
    for line in sys.stdin:
        if line[0].isalpha():
            sys.stderr.write(f'>{line}')
            #text = line
            continue
        data = line.split(fs)
        for d in data:
            try:
                values.append(int(d))
                cnt += 1
                smps += 1
            except ValueError:
                ...
            if cnt >= 400:  # 1000
                    plot(float(min),float(max),values,cnt,smps,text)
                    cnt = 0
                    values = []


def main():
    fs = ' '
    if len(sys.argv) <= 1:
        raise Exception("""Usage: {} [options] > serial-printer
          -i imagefile              print bitmap
          -b 'code barcode-string'  e.g. -b 'UPC-A 012345012345'
          -p 'min max'              moving-paper oscillograph
          -s '<field separator>'
        """.format(sys.argv[0]))
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'i:b:s:p:')
    except getopt.GetoptError as err:
        print(err)
        raise Exception()
    for o,a in opts:
        if o == '-i':
            subprocess.run(['convert','-resize',str(MAX_WIDTH),'-monochrome',a,TMP_PGM],check=True)
            image(TMP_PGM)
        if o == '-b':
            barcode(a)
        if o == '-s':
            fs = a
        if o == '-p':
            parse(a,fs)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGQUIT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)
    try:
        res = main()
    except subprocess.CalledProcessError as error:
        sys.stderr.write("\x1b[31;1m[subprocess]\x1b[0m \x1b[31m%s\x1b[0m\n" % error.stderr)
        res = error.returncode
    except FileNotFoundError as error:
        sys.stderr.write("\x1b[31;1m[pillow]\x1b[0m \x1b[31m%s\x1b[0m\n" % error.stderr)
    except Exception as error:
        sys.stderr.write(str(error))
        res = 1
    except KeyboardInterrupt:
        res = 0

    sys.exit(res)


