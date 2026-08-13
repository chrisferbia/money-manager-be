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
  .muted { color: #666; }
  .pill { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 999px; background: #eee; }
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
    <thead><tr><th>Name</th><th>Type</th><th>Balance</th><th>Created</th><th></th></tr></thead>
    <tbody>
      {% for account in accounts %}
      <tr>
        <td>{{ account.name }}</td>
        <td>{{ account.type }}</td>
        <td>{% if account.balance is defined %}{{ account.balance }}{% else %}<span class="muted">-</span>{% endif %}</td>
        <td>{{ account.created_at }}</td>
        <td class="actions">
          <a href="/ui/accounts/{{ account.id }}/edit">Edit</a>
          <form class="inline" method="post" action="/ui/accounts/{{ account.id }}/delete">
            <button type="submit">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="5">No accounts yet.</td></tr>
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

EXPENSES_BY_CATEGORY = """
<!doctype html>
<html>
<head><title>Expenses by Category</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Expenses by Category</h1>

  <form method="get" action="/ui/reports/expenses-by-category">
    <label>From<input type="text" name="from" value="{{ from_value }}"></label>
    <label>To<input type="text" name="to" value="{{ to_value }}"></label>
    <button type="submit">Filter</button>
  </form>

  <table>
    <thead><tr><th>Category</th><th>Total</th></tr></thead>
    <tbody>
      {% for item in report %}
      <tr>
        <td>{{ item.name }}</td>
        <td>{{ item.total }}</td>
      </tr>
      {% else %}
      <tr><td colspan="2">No matching expenses.</td></tr>
      {% endfor %}
    </tbody>
  </table>
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
    "home.html": """
<!doctype html>
<html>
<head><title>Money Manager</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Money Manager</h1>

  <nav class="actions">
    <a href="/">Dashboard</a>
    <a href="/ui/accounts">Accounts</a>
    <a href="/ui/transactions">Transactions</a>
    <a href="/ui/categories">Categories</a>
    <a href="/ui/reports/expenses-by-category">Reports</a>
  </nav>

  <table>
    <thead><tr><th>Total balance</th><th>Recent income</th><th>Recent expense</th></tr></thead>
    <tbody>
      <tr><td>{{ total_balance }}</td><td>{{ total_income }}</td><td>{{ total_expense }}</td></tr>
    </tbody>
  </table>

  <fieldset>
    <legend>Quick actions</legend>
    <p><a href="/ui/transactions">Add transaction</a></p>
    <p><a href="/ui/transactions">Transfer money</a></p>
    <p><a href="/ui/accounts">Add account</a></p>
  </fieldset>

  <h2>Accounts</h2>
  <table>
    <thead><tr><th>Name</th><th>Type</th><th>Balance</th></tr></thead>
    <tbody>
      {% for account in accounts %}
      <tr><td>{{ account.name }}</td><td>{{ account.type }}</td><td>{{ account.balance }}</td></tr>
      {% else %}
      <tr><td colspan="3">No accounts yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <h2>Recent activity</h2>
  <table>
    <thead><tr><th>Type</th><th>From</th><th>To</th><th>Amount</th><th>Occurred</th></tr></thead>
    <tbody>
      {% for transaction in recent_transactions %}
      <tr>
        <td>{{ transaction.type }}</td>
        <td>{{ account_names[transaction.account_id] }}</td>
        <td>{% if transaction.type == "transfer" and transaction.related_account_id %}{{ account_names[transaction.related_account_id] }}{% else %}<span class="muted">-</span>{% endif %}</td>
        <td>{{ transaction.amount }}</td>
        <td>{{ transaction.occurred_at }}</td>
      </tr>
      {% else %}
      <tr><td colspan="5">No transactions yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <h2>Reports preview</h2>
  <table>
    <thead><tr><th>Category</th><th>Total</th></tr></thead>
    <tbody>
      {% for item in report %}
      <tr><td>{{ item.name }}</td><td>{{ item.total }}</td></tr>
      {% else %}
      <tr><td colspan="2">No matching expenses.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
""",
    "accounts_list.html": ACCOUNTS_LIST,
    "account_edit.html": ACCOUNT_EDIT,
    "categories_list.html": CATEGORIES_LIST,
    "category_edit.html": CATEGORY_EDIT,
    "expenses_by_category.html": EXPENSES_BY_CATEGORY,
    "transactions_list.html": """
<!doctype html>
<html>
<head><title>Transactions</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Transactions</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  <table>
    <thead><tr><th>Type</th><th>Account</th><th>Category</th><th>Related</th><th>Amount</th><th>Occurred</th><th></th></tr></thead>
    <tbody>
      {% for transaction in transactions %}
      <tr>
        <td>{{ transaction.type }}</td>
        <td>
          {% for account in accounts %}
            {% if account.id == transaction.account_id %}{{ account.name }}{% endif %}
          {% endfor %}
        </td>
        <td>
          {% if transaction.category_id %}
            {% for category in categories %}
              {% if category.id == transaction.category_id %}{{ category.name }}{% endif %}
            {% endfor %}
          {% else %}<span class="muted">-</span>{% endif %}
        </td>
        <td>
          {% if transaction.type == "transfer" and transaction.related_account_id %}
            {% for account in accounts %}
              {% if account.id == transaction.related_account_id %}to {{ account.name }}{% endif %}
            {% endfor %}
          {% else %}<span class="muted">-</span>{% endif %}
        </td>
        <td>{{ transaction.amount }}</td>
        <td>{{ transaction.occurred_at }}</td>
        <td class="actions">
          <a href="/ui/transactions/{{ transaction.id }}/edit">Edit</a>
          <form class="inline" method="post" action="/ui/transactions/{{ transaction.id }}/delete">
            <button type="submit">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="7">No transactions yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <fieldset>
    <legend>Add transaction</legend>
    <form method="post" action="/ui/transactions">
      <label>Type
        <select name="type">
          <option value="income" {% if form.type == "income" %}selected{% endif %}>income</option>
          <option value="expense" {% if form.type == "expense" %}selected{% endif %}>expense</option>
          <option value="transfer" {% if form.type == "transfer" %}selected{% endif %}>transfer</option>
        </select>
      </label>
      <label>Account
        <select name="account_id" required>
          <option value="">Select an account</option>
          {% for account in accounts %}
          <option value="{{ account.id }}" {% if form.account_id|string == account.id|string %}selected{% endif %}>{{ account.name }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Destination account
        <select name="related_account_id">
          <option value="">None</option>
          {% for account in accounts %}
          <option value="{{ account.id }}" {% if form.related_account_id|string == account.id|string %}selected{% endif %}>{{ account.name }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Category
        <select name="category_id">
          <option value="">None</option>
          {% for category in categories %}
          <option value="{{ category.id }}" {% if form.category_id|string == category.id|string %}selected{% endif %}>{{ category.name }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Amount (minor units)<input type="number" name="amount" min="1" value="{{ form.amount }}" required></label>
      <label>Description<input type="text" name="description" value="{{ form.description }}"></label>
      <label>Occurred at<input type="text" name="occurred_at" value="{{ form.occurred_at }}" placeholder="2026-08-13T12:34:56Z"></label>
      <button type="submit">Add</button>
    </form>
  </fieldset>
</body>
</html>
""",
    "transaction_edit.html": """
<!doctype html>
<html>
<head><title>Edit Transaction</title>""" + BASE_STYLE + """</head>
<body>
  <h1>Edit Transaction</h1>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

    <form method="post" action="/ui/transactions/{{ transaction.id }}/edit">
      <p class="muted">{% if transaction.type == "transfer" %}Transfer from account {{ transaction.account_id }} to account {{ transaction.related_account_id }}{% else %}Type: {{ transaction.type }} | Account ID: {{ transaction.account_id }}{% endif %}</p>
      <label>Category
        <select name="category_id">
          <option value="">None</option>
          {% if transaction.type != "transfer" %}
          {% for category in categories %}
          <option value="{{ category.id }}" {% if transaction.category_id and transaction.category_id == category.id %}selected{% endif %}>{{ category.name }}</option>
          {% endfor %}
          {% endif %}
        </select>
      </label>
      <label>Amount (minor units)<input type="number" name="amount" min="1" value="{{ transaction.amount }}" required></label>
      <label>Description<input type="text" name="description" value="{{ transaction.description or '' }}"></label>
      <label>Occurred at<input type="text" name="occurred_at" value="{{ transaction.occurred_at }}"></label>
    <button type="submit">Save</button>
  </form>

  <p><a href="/ui/transactions">Back to transactions</a></p>
</body>
</html>
""",
}
