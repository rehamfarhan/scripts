#!/usr/bin/env python3

# Text to Morse Code Generator with custom symbols

MORSE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',   'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',    'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',   'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',    'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',

    '0': '-----',  '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....',  '6': '-....', '7': '--...', '8': '---..', '9': '----.',

    '.': '.-.-.-', ',': '--..--', '?': '..--..', "'": '.----.',
    '!': '-.-.--', '/': '-..-.',  '(': '-.--.',  ')': '-.--.-',
    '&': '.-...',  ':': '---...', ';': '-.-.-.', '=': '-...-',
    '+': '.-.-.',  '-': '-....-', '_': '..--.-', '"': '.-..-.',
    '$': '...-..-', '@': '.--.-.'
}

def to_morse(text, dot_symbol, dash_symbol, space_symbol):
    words = text.upper().split()
    encoded_words = []

    for word in words:
        encoded_letters = []
        for char in word:
            if char in MORSE:
                morse = MORSE[char]
                morse_custom = morse.replace('.', dot_symbol).replace('-', dash_symbol)
                encoded_letters.append(morse_custom)
        encoded_words.append(space_symbol.join(encoded_letters))

    return (space_symbol * 3).join(encoded_words)

# Input from user
dot_symbol = input("What should the DOT character be? ")
dash_symbol = input("What should the DASH character be? ")
space_symbol = input("What should the SPACE character be? ")

text = input("Enter text to convert: ")

result = to_morse(text, dot_symbol, dash_symbol, space_symbol)
print("\nEncrypted Morse:")
print(result)
