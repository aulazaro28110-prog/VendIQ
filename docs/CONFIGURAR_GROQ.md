# Conectar el LLM (Groq) — 3 minutos

VendIQ funciona **sin esto**. Si no hay clave, los mensajes los escribe
`07_redactor.py` y todo lo demás es idéntico: las mismas tres acciones, los mismos
botones, el mismo registro de dudas. El modelo mejora **cómo suenan** los mensajes,
no **lo que el bot puede decir**.

## 1. Sacar la clave

1. Entra en **console.groq.com** y crea la cuenta. Es gratis y no pide tarjeta.
2. Menú **API Keys** → **Create API Key**.
3. Cópiala. Empieza por `gsk_`.

## 2. Guardarla

Crea un fichero llamado **`.env`** en la carpeta del proyecto (junto a
`06_panel.py`) con este contenido:

```
GROQ_API_KEY=gsk_lo_que_te_haya_dado_groq
```

Y el modelo, una línea más (opcional — si falta se usa el de por defecto):

```
GROQ_MODELO=openai/gpt-oss-120b
```

Groq retira modelos con cierta frecuencia: `llama-3.3-70b-versatile`, que era el
de por defecto, lo apagaron el 16/08/2026. Si un día la API contesta 404, es eso:
mira los modelos vivos en console.groq.com y cambia esta línea. El bot no se cae
—sigue redactando `07_redactor.py`— pero el panel lo dirá.

En PowerShell, desde la carpeta del proyecto:

```powershell
Set-Content -Path .env -Value "GROQ_API_KEY=gsk_tu_clave_aqui" -Encoding utf8
```

## 3. Comprobar

```powershell
python 06_panel.py
```

Al arrancar dice cuál de los dos está redactando:

```
Redacta: Groq (openai/gpt-oss-120b)
```

o bien

```
Redacta: redactor determinista — sin GROQ_API_KEY en .env
```

En el simulador de chat, debajo de la acción, cada respuesta indica quién la
escribió.

---

## Lo que NO cambia al conectar el modelo

Esto es lo importante y es lo que hay que saber explicar:

**Al modelo no se le pasa el precio si la búsqueda no lo ha autorizado.** No es que
se le pida que no lo diga: es que no lo tiene. Ver `_mensajes()` en
`08_conversar.py`.

Y por si acaso, hay una segunda barrera: **se leen todos los importes del mensaje
que escribe el modelo y se contrastan con los autorizados**. Si aparece uno que no
lo está, se tira la redacción del modelo y sale el borrador determinista. El panel
lo dice en rojo en vez de disimularlo.

Las tres acciones (RESPONDER / PREGUNTAR / ESCALAR) las decide el código. El modelo
redacta dentro de la acción ya elegida. Si el modelo decidiera, los guardarraíles
solo se podrían comprobar por estadística; como están, se comprueban por
construcción.

## Seguridad

- `.env` está en `.gitignore`. No se sube nunca.
- No pegues la clave en un chat ni en un commit.
- Si se te escapa, en console.groq.com puedes revocarla y crear otra.
