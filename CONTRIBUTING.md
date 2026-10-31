# Contribuir

Gracias por querer mejorar TDT local. Esto empezó como un cacharro personal y hoy es público porque os
interesó, así que **cualquier ayuda es bienvenida**: una *issue* que diga «esto no me va», una idea, una
corrección de una errata, un *pull request* de cien líneas o un comentario sincero sobre lo mal que está
algo. No hace falta pedir permiso para empezar; si el cambio es grande, una *issue* antes ahorra disgustos.

Es un proyecto pequeño y con una norma principal: **cero dependencias en ejecución** (solo la biblioteca
estándar de Python y JavaScript del navegador).

## Licencia de tus contribuciones

TDT local es Apache 2.0. Al enviar un cambio aceptas que se publique bajo esa licencia (sección 5 de la
licencia). Si añades código o recursos de terceros, comprueba que su licencia es compatible con Apache 2.0 y
añádelos a `NOTICE` y a la página de créditos (`tdtlocal/static/about.html`).

## Preparar el entorno

```
git clone <tu fork>
cd tdt-local
python -m pip install ruff pytest     # opcional: solo para el lint y para ejecutar las pruebas con pytest
python scripts/check.py               # lint + pruebas de Python + pruebas del navegador
```

Las pruebas de Python usan `unittest` y no necesitan nada instalado:
`python -m unittest discover -s tests -t .`. Las del navegador usan `node --test` (Node 20 o superior).

## Antes de enviar un cambio

1. **Pruebas.** Todo cambio de comportamiento lleva su prueba, y un error corregido, una que lo
   habría detectado. La red, los modelos y ffmpeg se simulan; las pruebas no deben tocar internet.
2. **Estilo.** `ruff check .` y `ruff format --check .` sin avisos. Líneas de hasta 120 caracteres.
3. **Código del navegador.** Lo que se pueda expresar como función pura va a `static/js/lib/` y se
   prueba en `tests/js/`. Sin dependencias, sin *bundler*, sin scripts ni estilos en línea (la CSP
   los bloquea).
4. **Seguridad.** Las peticiones que hace el proxy pasan por `Net`; no abras conexiones salientes
   por otro camino. Lo que viene de la red o del modelo de IA se valida antes de usarse.
5. **Idioma.** Interfaz, mensajes al usuario y documentación en español; identificadores, comentarios
   y docstrings en inglés.
6. **Compatibilidad.** Python 3.9 o superior. Nada de sintaxis o módulos posteriores.

## Commits y revisión

- Mensajes en imperativo y con el *qué* y el *porqué* en la primera línea.
- Un cambio por *pull request*; si toca varias cosas, mejor varias.
- Rellena la plantilla del *pull request*: qué cambia, cómo lo has probado y si afecta a la seguridad.

## Informar de un error

Abre una *issue* con la versión (`python -m tdtlocal --version`), el sistema operativo, el canal
afectado y lo que sale en la consola del servidor. Si es un problema de seguridad, **no** abras una
*issue* pública: mira [SECURITY.md](SECURITY.md).
