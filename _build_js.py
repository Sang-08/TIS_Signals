import os

js_content = open('_appjs_template.txt','r',encoding='utf-8').read()
with open('dashboard/app.js','w',encoding='utf-8') as f:
    f.write(js_content)
print("app.js written OK")