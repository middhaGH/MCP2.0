from flask import Flask, request, jsonify

app = Flask(__name__)

# Define the addition function
def add_numbers(a, b):
    return a + b

# Create an API route
@app.route('/add', methods=['POST'])
def add():
    data = request.get_json()  # get JSON data from the request
    a = data.get('a')
    b = data.get('b')
    
    # Check if both a and b are provided
    if a is None or b is None:
        return jsonify({"error": "Please provide both 'a' and 'b' numbers."}), 400
    
    try:
        a = float(a)
        b = float(b)
    except ValueError:
        return jsonify({"error": "Inputs must be numbers."}), 400

    result = add_numbers(a, b)
    
    return jsonify({"sum": result})

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
