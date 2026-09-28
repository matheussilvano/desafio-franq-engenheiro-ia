.PHONY: install run test lint

install:
	python3 -m pip install -r requirements.txt
run:
	streamlit run app.py
test:
	python3 -m pytest -q
lint:
	python3 -m compileall -q data_assistant app.py
