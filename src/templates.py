BASE_STYLE = """
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; color: #1a1a1a; }
  h1 { font-size: 1.4rem; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }
  th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #ddd; }
  form.inline { display: inline; }
  .error { color: #b00020; margin-bottom: 1rem; }
  .actions a, .actions button { margin-right: 0.5rem; }
  fieldset { border: 1px solid #ddd; padding: 1rem; }
  label { display: block; margin-top: 0.5rem; }
  input, select { padding: 0.3rem; width: 100%; box-sizing: border-box; }
  button { margin-top: 1rem; padding: 0.4rem 1rem; }
</style>
"""

ACCOUNTS_LIST = """
<!doctype html>
<html>
<head><title>Accounts</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Accounts</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  <table>
    <thead><tr><th>Name</th><th>Type</th><th>Created</th><th></th></tr></thead>
    <tbody>
      {% for account in accounts %}
      <tr>
        <td>{{ account.name }}</td>
        <td>{{ account.type }}</td>
        <td>{{ account.created_at }}</td>
        <td class="actions">
          <a href="/ui/accounts/{{ account.id }}/edit">Edit</a>
          <form class="inline" method="post" action="/ui/accounts/{{ account.id }}/delete">
            <button type="submit">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="4">No accounts yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <fieldset>
    <legend>Add account</legend>
    <form method="post" action="/ui/accounts">
      <label>Name<input type="text" name="name" value="{{ form_name }}" required></label>
      <label>Type
        <select name="type">
          <option value="cash" {% if form_type == "cash" %}selected{% endif %}>cash</option>
          <option value="debit_card" {% if form_type == "debit_card" %}selected{% endif %}>debit_card</option>
        </select>
      </label>
      <button type="submit">Add</button>
    </form>
  </fieldset>
</body>
</html>
"""

CATEGORIES_LIST = """
<!doctype html>
<html>
<head><title>Categories</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Categories</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  <table>
    <thead><tr><th>Name</th><th>Created</th><th></th></tr></thead>
    <tbody>
      {% for category in categories %}
      <tr>
        <td>{{ category.name }}</td>
        <td>{{ category.created_at }}</td>
        <td class="actions">
          <a href="/ui/categories/{{ category.id }}/edit">Edit</a>
          <form class="inline" method="post" action="/ui/categories/{{ category.id }}/delete">
            <button type="submit">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="3">No categories yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <fieldset>
    <legend>Add category</legend>
    <form method="post" action="/ui/categories">
      <label>Name<input type="text" name="name" value="{{ form_name }}" required></label>
      <button type="submit">Add</button>
    </form>
  </fieldset>
</body>
</html>
"""

CATEGORY_EDIT = """
<!doctype html>
<html>
<head><title>Edit Category</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Edit Category</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  <form method="post" action="/ui/categories/{{ category.id }}/edit">
    <label>Name<input type="text" name="name" value="{{ category.name }}" required></label>
    <button type="submit">Save</button>
  </form>

  <p><a href="/ui/categories">Back to categories</a></p>
</body>
</html>
"""

ACCOUNT_EDIT = """
<!doctype html>
<html>
<head><title>Edit Account</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Edit Account</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  <form method="post" action="/ui/accounts/{{ account.id }}/edit">
    <label>Name<input type="text" name="name" value="{{ account.name }}" required></label>
    <label>Type
      <select name="type">
        <option value="cash" {% if account.type == "cash" %}selected{% endif %}>cash</option>
        <option value="debit_card" {% if account.type == "debit_card" %}selected{% endif %}>debit_card</option>
      </select>
    </label>
    <button type="submit">Save</button>
  </form>

  <p><a href="/ui/accounts">Back to accounts</a></p>
</body>
</html>
"""

TEMPLATES = {
    "accounts_list.html": ACCOUNTS_LIST,
    "account_edit.html": ACCOUNT_EDIT,
    "categories_list.html": CATEGORIES_LIST,
    "category_edit.html": CATEGORY_EDIT,
}
