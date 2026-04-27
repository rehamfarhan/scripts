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

REVERSE = {v: k for k, v in MORSE.items()}


# ---------------- ENCODE ----------------
def encode(text, dot, dash, space):
    words = text.upper().split()
    out_words = []

    for word in words:
        letters = []
        for ch in word:
            if ch in MORSE:
                code = MORSE[ch]
                code = code.replace('.', dot).replace('-', dash)
                letters.append(code)
        out_words.append(space.join(letters))

    return (space * 3).join(out_words)


# ---------------- DECODE (FIXED SYMMETRY) ----------------
def decode(code, dot, dash, space):
    # Step 1: restore standard morse BEFORE splitting
    code = code.replace(dot, '.').replace(dash, '-')

    word_sep = space * 3
    letter_sep = space

    words = code.split(word_sep)
    result = []

    for word in words:
        letters = word.split(letter_sep)
        decoded_word = []

        for letter in letters:
            if letter in REVERSE:
                decoded_word.append(REVERSE[letter])

        result.append("".join(decoded_word))

    return " ".join(result)


# ---------------- CLI ----------------
if len(sys.argv) < 2:
    print("Usage:")
    print("  morsegen <text>")
    print("  morsegen --decode <morse>")
    sys.exit(1)

mode = sys.argv[1]

dot = input("Dot symbol: ")
dash = input("Dash symbol: ")
space = input("Space symbol: ")

# ---------------- ROUTING ----------------
if mode == "--decode":
    if len(sys.argv) < 3:
        print("Error: no morse text provided")
        sys.exit(1)

    morse_input = " ".join(sys.argv[2:])
    print("\nDecoded Text:\n")
    print(decode(morse_input, dot, dash, space))

else:
    text = " ".join(sys.argv[1:])
    print("\nEncoded Morse:\n")
    print(encode(text, dot, dash, space))

