from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import requests
from datetime import date
import re
from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
app = Flask(__name__, template_folder="Blueprint")
app.secret_key = "dev-secret-key-change-me"

API_BASE = "https://themealdb.com/api/json/v1/1"


def search_by_ingredient(ingredient):
   
    try:
        url = f"{API_BASE}/filter.php?i={ingredient}"
        r = requests.get(url, timeout=5)
        data = r.json()

        if data["meals"]:
            return data["meals"]

        return []

    except Exception as e:
        print("API error:", e)
        return []


def get_recipe_details(meal_id):
    """Fetch full recipe info."""
    try:
        url = f"{API_BASE}/lookup.php?i={meal_id}"
        r = requests.get(url, timeout=5)

        meal = r.json()["meals"][0]

        ingredients = []

        for i in range(1, 21):
            ing = meal.get(f"strIngredient{i}")
            if ing and ing.strip():
                ingredients.append(ing.strip())

        return {
            "title": meal["strMeal"],
            "image": meal["strMealThumb"],
            "category": meal["strCategory"],
            "area": meal["strArea"],
            "ingredients": ingredients,
            "steps": meal["strInstructions"].split("\r\n")
        }

    except Exception as e:
        print("Detail fetch error:", e)
        return None




@app.route("/")
def home():

    pantry = session.get("ingredients", [])

    return render_template(
        "home.html",
        ingredient_count=len(pantry),
        ingredients=pantry[:8]
    )



@app.route("/ingredients", methods=["GET", "POST"])
def ingredients():

    if "ingredients" not in session:
        session["ingredients"] = []

    if request.method == "POST":

        action = request.form.get("action")
        item = (request.form.get("ingredient") or "").strip()

        if action == "add" and item:

            current = session["ingredients"]

            if item.lower() not in [x.lower() for x in current]:
                session["ingredients"] = current + [item]

        elif action == "remove":

            remove_item = request.form.get("remove_item")

            session["ingredients"] = [
                x for x in session["ingredients"]
                if x.lower() != remove_item.lower()
            ]

        elif action == "clear":

            session["ingredients"] = []

        return redirect(url_for("ingredients"))

    return render_template(
        "ingredients.html",
        ingredients=session.get("ingredients", [])
    )






def clean_steps(steps_list):
    
    clean = []
    for s in steps_list:
    
        s = re.sub(r"^\d+\.\s*", "", s)
        if s.strip():
            clean.append(s.strip())
    return clean


@app.route("/Output", methods=["GET", "POST"])
def Output():
    pantry = session.get("ingredients", [])
    recipes = []

    if not pantry:
        return render_template(
            "Output.html",
            recipes=[],
            ingredients=[],
            excluded=[],
            today=date.today().strftime("%B %d, %Y"),
            message="No ingredients in your pantry. Add some to see recipes!"
        )

    mode = request.args.get("mode", "strict")       
    exclude_raw = request.args.get("exclude", "")    
    exclude = [e.strip().lower() for e in exclude_raw.split(",") if e.strip()]

    pantry_lower = [p.lower() for p in pantry]

    
    main_ingredient = pantry[0]
    results = search_by_ingredient(main_ingredient)

    for meal in results[:10]:  
        recipe = get_recipe_details(meal["idMeal"])
        if not recipe:
            continue

        
        recipe["steps"] = clean_steps(recipe["steps"])

        recipe_ingredients_lower = [i.lower() for i in recipe["ingredients"]]

        
        if any(e in recipe_ingredients_lower for e in exclude):
            continue  

      
        if mode == "strict":
            
            if any(i not in pantry_lower for i in recipe_ingredients_lower):
                continue

       
        recipes.append(recipe)

   
    message = ""
    if not recipes:
        message = "No recipes found — try adding more ingredients or adjusting filters."

    return render_template(
        "Output.html",
        recipes=recipes,
        ingredients=pantry,
        excluded=exclude,
        today=date.today().strftime("%B %d, %Y"),
        message=message
    )




@app.route("/tryout", methods=["GET", "POST"])
def tryout():
    recipe = None
    exclude_raw = ""
    exclude = []

    if request.method == "POST":
        exclude_raw = request.form.get("exclude", "")
        exclude = [e.strip().lower() for e in exclude_raw.split(",") if e.strip()]

    try:
        
        for _ in range(15): 
            r = requests.get(f"{API_BASE}/random.php", timeout=5)
            meal = r.json()["meals"][0]

            ingredients = []
            for i in range(1, 21):
                ing = meal.get(f"strIngredient{i}")
                if ing and ing.strip():
                    ingredients.append(ing.strip())

            
            if any(e in [x.lower() for x in ingredients] for e in exclude):
                continue

            recipe = {
                "name": meal["strMeal"],
                "image": meal["strMealThumb"],
                "category": meal["strCategory"],
                "instructions": meal["strInstructions"],
                "ingredients": ingredients
            }
            break  

    except:
        recipe = None

    return render_template(
        "tryout.html",
        recipe=recipe,
        exclude=exclude_raw
    )




@app.route("/api/chat", methods=["POST"])
def api_chat():
    from groq import Groq
    import os

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    data = request.get_json()
    message = (data.get("message") or "").strip()

    pantry = session.get("ingredients", [])
    pantry_text = ", ".join(pantry) if pantry else "no ingredients saved"

    prompt = f"""
User ingredients: {pantry_text}

User question: {message}
"""



    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful cooking assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        reply = response.choices[0].message.content

        return jsonify({
            "reply": reply,
            "suggestions": []
        })

    except Exception as e:
        print("Groq API error:", e)

        return jsonify({
            "reply": "Sorry, I couldn't reach the AI service right now.",
            "suggestions": []
        })




if __name__ == "__main__":
    app.run(debug=True)