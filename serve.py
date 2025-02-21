from streamlit.web.cli import main

def app():
    # Override sys.argv to emulate running "streamlit run app.py"
    import sys
    sys.argv = ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    main()