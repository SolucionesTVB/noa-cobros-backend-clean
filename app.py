@app.route("/")
def home():
    return """
    <html>
      <head>
        <title>N – Backend</title>
        <style>
          body { font-family: Arial, sans-serif; background: #0d1117; color: #fff; text-align: center; padding: 50px; }
          h1 { color: #00d4ff; text-shadow: 0 0 10px #00d4ff; font-size: 48px; }
          p { font-size: 18px; line-height: 1.5; }
          b { color: #00ff88; }
          a { color: #00ff88; font-size: 18px; text-decoration: none; }
          a:hover { text-shadow: 0 0 5px #00ff88; }
        </style>
      </head>
      <body>
        <h1>N</h1>
        <p><b>Bienvenido al backend de Noa Cobros</b></p>
        <p><b>Este es el motor en Render</b>, encargado de procesar facturas y enviar notificaciones.</p>
        <p>La interfaz de usuario está en:<br>
          <a href="https://polite-gumdrop-ba6be7.netlify.app" target="_blank">
            👉 Ir al Frontend de Noa Cobros
          </a>
        </p>
        <p style="margin-top:30px; font-size:12px; color:#aaa;">
          Marca blanca – Listo para producción
        </p>
      </body>
    </html>
    """
