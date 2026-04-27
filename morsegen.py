#!/usr/bin/env python3
import sys
import argparse

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


# ---------------- VALIDATION ----------------
def validate(dot, dash, sep):
    if len({dot, dash, sep}) != 3:
        raise ValueError("dot, dash, and separator must be distinct.")

    for a, b in [(dot, dash), (dot, sep), (dash, sep)]:
        if a in b or b in a:
            raise ValueError("symbols must not overlap or contain each other.")


# ---------------- ENCODE ----------------
def encode(text, dot, dash, sep):
    words = text.upper().split()
    out = []

    for word in words:
        letters = []
        for ch in word:
            if ch in MORSE:
                code = MORSE[ch].replace('.', dot).replace('-', dash)
                letters.append(code)
        out.append(sep.join(letters))

    return (sep * 3).join(out)


# ---------------- DECODE ----------------
def decode(code, dot, dash, sep):
    code = code.replace(dot, '.').replace(dash, '-')

    words = code.split(sep * 3)
    out = []

    for word in words:
        letters = word.split(sep)
        decoded = []
        for l in letters:
            if l in REVERSE:
                decoded.append(REVERSE[l])
        out.append("".join(decoded))

    return " ".join(out)


# ---------------- ARGPARSE ----------------
def build_parser():
    parser = argparse.ArgumentParser(prog="morsegen")

    subparsers = parser.add_subparsers(dest="command")

    # encode subcommand
    enc = subparsers.add_parser("encode", aliases=["ecd"])
    enc.add_argument("text", nargs="+")

    # decode subcommand
    dec = subparsers.add_parser("decode", aliases=["dcd"])
    dec.add_argument("text", nargs="+")

    # shared args
    for p in [parser, enc, dec]:
        p.add_argument("--dot", "-t", default=".")
        p.add_argument("--dash", "-h", default="-")
        p.add_argument("--separator", "--sep", "-s", default=" ")

    # flags mode
    parser.add_argument("--decode", "-d", action="store_true")
    parser.add_argument("--encode", "-e", action="store_true")

    parser.add_argument("text", nargs="*")

    return parser


# ---------------- MAIN ----------------
def main():
    parser = build_parser()
    args = parser.parse_args()

    dot = args.dot
    dash = args.dash
    sep = args.separator

    try:
        validate(dot, dash, sep)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # --- subcommand mode ---
    if args.command in ["encode", "ecd"]:
        text = " ".join(args.text)
        print(encode(text, dot, dash, sep))
        return

    if args.command in ["decode", "dcd"]:
        text = " ".join(args.text)
        print(decode(text, dot, dash, sep))
        return

    # --- flag mode ---
    text = " ".join(args.text)

    if args.decode:
        print(decode(text, dot, dash, sep))
    else:
        # default = encode
        print(encode(text, dot, dash, sep))


if __name__ == "__main__":
    main()

