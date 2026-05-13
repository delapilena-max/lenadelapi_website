import moviepy, os
print('moviepy.__file__:', moviepy.__file__)
print('moviepy.__path__:', moviepy.__path__)
print('contents:', os.listdir(moviepy.__path__[0]))
