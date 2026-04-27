#!/usr/bin/env python3
import sys

MORSE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',

    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',

    '.': '.-.-.-', ',': '--..--', '?': '..--..', "'": '.----.',
    '!': '-.-.--', '/': '-..-.',  '(': '-.--.',  ')': '-.--.-',
    '&': '.-...',  ':': '---...', ';': '-.-.-.', '=': '-...-',
    '+': '.-.-.',  '-': '-....-', '_': '..--.-', '"': '.-..-.',
    '$': '...-..-', '@': '.--.-.'
}

def to_morse(text, dot, dash, space):
    words = text.upper().split()
    result_words = []

    for word in words:
        letters = []
        for ch in word:
            if ch in MORSE:
                code = MORSE[ch]
                code = code.replace('.', dot).replace('-', dash)
                letters.append(code)
        result_words.append(space.join(letters))

    return (space * 3).join(result_words)

# --- CLI ARG HANDLING ---
if len(sys.argv) < 2:
    print("Usage: morsegen <text-to-encrypt>")
    sys.exit(1)

text = " ".join(sys.argv[1:])

dot = input("Dot symbol: ")
dash = input("Dash symbol: ")
space = input("Space symbol: ")

print("\nEncrypted Morse:\n")
print(to_morse(text, dot, dash, space))
