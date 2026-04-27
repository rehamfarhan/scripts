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

REVERSE_MORSE = {v: k for k, v in MORSE.items()}

WORD_PLACEHOLDER = "\uE000"
LETTER_PLACEHOLDER = "\uE001"
DOT_PLACEHOLDER = "\uE002"
DASH_PLACEHOLDER = "\uE003"

def usage():
    print("Usage:")
    print("  morsegen <text>")
    print("  morsegen -d <morse-text>")
    print("  morsegen --decode <morse-text>")

def validate_symbols(dot, dash, space):
    if not dot or not dash or not space:
        raise ValueError("Dot, dash, and space cannot be empty.")

    if len({dot, dash, space}) != 3:
        raise ValueError("Dot, dash, and space must all be different.")

    symbols = {
        "dot": dot,
        "dash": dash,
        "space": space
    }

    for name_a, a in symbols.items():
        for name_b, b in symbols.items():
            if name_a == name_b:
                continue
            if a in b or b in a:
                raise ValueError(
                    f"'{name_a}' and '{name_b}' cannot overlap or contain each other."
                )


def prompt_symbols():
    while True:
        dot = input("Dot symbol: ")
        dash = input("Dash symbol: ")
        space = input("Space symbol: ")

        try:
            validate_symbols(dot, dash, space)
            return dot, dash, space
        except ValueError as e:
            print(f"\nInvalid symbol set: {e}")
            print("Please try again.\n")


def encode_text(text, dot, dash, space):
    words = text.split()
    encoded_words = []
    skipped_chars = []

    for word in words:
        encoded_letters = []
        for ch in word.upper():
            if ch in MORSE:
                morse = MORSE[ch]
                morse = morse.replace('.', dot).replace('-', dash)
                encoded_letters.append(morse)
            else:
                skipped_chars.append(ch)

        if encoded_letters:
            encoded_words.append(space.join(encoded_letters))

    if skipped_chars:
        unique = "".join(sorted(set(skipped_chars)))
        print(f"Warning: skipped unsupported characters: {unique}")

    return (space * 3).join(encoded_words)


def decode_text(code, dot, dash, space):
    # Replace the custom tokens with safe placeholders first.
    # This makes decoding much more reliable with custom symbols.
    ordered_tokens = sorted(
        [
            (space * 3, WORD_PLACEHOLDER),
            (space, LETTER_PLACEHOLDER),
            (dot, DOT_PLACEHOLDER),
            (dash, DASH_PLACEHOLDER),
        ],
        key=lambda item: len(item[0]),
        reverse=True
    )

    temp = code
    for old, new in ordered_tokens:
        temp = temp.replace(old, new)

    temp = temp.replace(DOT_PLACEHOLDER, ".")
    temp = temp.replace(DASH_PLACEHOLDER, "-")

    words = temp.split(WORD_PLACEHOLDER)
    decoded_words = []

    for word in words:
        letters = [x for x in word.split(LETTER_PLACEHOLDER) if x]
        decoded_letters = []

        for letter in letters:
            if letter in REVERSE_MORSE:
                decoded_letters.append(REVERSE_MORSE[letter])
            else:
                raise ValueError(f"Invalid Morse pattern found: {letter}")

        decoded_words.append("".join(decoded_letters))

    return " ".join(decoded_words)


def main():
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    mode = sys.argv[1]

    DECODE_FLAGS = ["-d", "--decode"]
    is_decode = mode in DECODE_FLAGS

    try:
        dot, dash, space = prompt_symbols()

        if is_decode:
            if len(sys.argv) < 3:
                raise ValueError("No Morse text provided for decoding.")

            morse_input = " ".join(sys.argv[2:])
            result = decode_text(morse_input, dot, dash, space)

            print("\nDecoded Text:\n")
            print(result)
        else:
            text = " ".join(sys.argv[1:])
            result = encode_text(text, dot, dash, space)

            print("\nEncoded Morse:\n")
            print(result)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
