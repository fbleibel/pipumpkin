"""
A simple test of the pyttsx engine and espeak. This is the default
example of pyttsx.
"""
def main():
    import pyttsx
    engine = pyttsx.init()
    engine.say('Sally sells seashells by the seashore.')
    engine.say('The quick brown fox jumped over the lazy dog.')
    engine.runAndWait()

if __name__ == "__main__":
    main()
