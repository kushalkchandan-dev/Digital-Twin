# 1. Go to project folder
cd "C:\Users\kusha\OneDrive\Desktop\CN Imp"

# 2. Create and activate venv
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Train AI (first time only)
python main.py --train

# 5. Run the project
python main.py

# 6. Open browser to http://127.0.0.1:5000
