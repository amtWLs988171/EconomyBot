from gradio_client import Client, handle_file
from PIL import Image
import os

if not os.path.exists("sample.jpg"):
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save('sample.jpg')

client = Client("SmilingWolf/wd-tagger")

print("predicting...")
try:
    # Mimic exactly what broker.py does
    result = client.predict(
        handle_file('sample.jpg'),
        api_name="/predict"
    )
    print("Result Type:", type(result))
    
    if isinstance(result, (list, tuple)):
        print(f"Result Length: {len(result)}")
        for i, item in enumerate(result):
             print(f"--- Item {i} ({type(item)}) ---")
             # Truncate if too long
             s_item = str(item)
             if len(s_item) > 500:
                 print(s_item[:500] + "...")
             else:
                 print(s_item)
    else:
        print("Result:", result)

except Exception as e:
    print("Error:", e)
