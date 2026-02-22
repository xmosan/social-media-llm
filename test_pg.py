import urllib.parse
import psycopg2
import os

db_url = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"
result = urllib.parse.urlparse(db_url)

conn = psycopg2.connect(
    database=result.path[1:],
    user=result.username,
    password=result.password,
    host=result.hostname,
    port=result.port
)

cur = conn.cursor()
cur.execute("SELECT id, email, is_superadmin, length(password_hash) FROM users;")
rows = cur.fetchall()
print(f"Total users: {len(rows)}")
for r in rows:
    print(r)

cur.close()
conn.close()
