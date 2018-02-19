# Babel

Notes on updating Babel translations...

1. Extracting strings

    ```
    pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
    ```

2. Inital add language

    ```
    pybabel init -i messages.pot -d translations -l de
    ```

3. Compile language

    ```
    pybabel compile -d translations
    ```
    
4. Update transcripts

    First do step 1, then:
    ```
    pybabel update -i messages.pot -d translations
    ```
    Then fix files in translations and do step 3.