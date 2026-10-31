# Seguridad

## Antes de nada: sed prudentes

TDT local es una versión incipiente, de uso personal y «vibecodeada» con IA. Tiene defensas y pruebas, pero no ha
pasado ninguna auditoría: **supón que hay agujeros** y no lo expongas a internet. Que alguien los encuentre y me
avise es justo lo que se agradece. Gracias de antemano.

## Modelo de amenazas

TDT local está pensado para ejecutarse en **tu propio equipo**, escuchando solo en `127.0.0.1`.
Defiende de:

- páginas web de otros sitios que intenten usar el servidor local (comprobación de `Host`,
  `Origin` y `Sec-Fetch-Site`, y política `frame-ancestors 'none'`);
- *SSRF* a través del proxy (lista de hosts permitidos, solo `http(s)`, direcciones no públicas
  siempre bloqueadas, también en las redirecciones);
- cambios de configuración desde otros equipos de la red (los ajustes, la descarga de modelos y las pruebas de
  conexión solo aceptan peticiones del propio equipo, porque `whisper_bin` es un programa que se ejecuta);
- rutas fuera de `tdtlocal/static/` (*path traversal*);
- XML con entidades en las guías (se rechaza) y descargas de tamaño desmesurado (hay límites);
- respuestas inesperadas del modelo de IA (se validan; solo se aceptan acciones y canales ofrecidos).

**No** defiende, por diseño, de alguien con acceso a tu sesión o a tu red local cuando usas
`--lan`: ese modo no tiene autenticación y debe usarse solo en redes de confianza.

## Cómo informar de una vulnerabilidad

Por favor, no publiques los detalles de entrada. Abre una *issue* que diga solo «he encontrado un problema de
seguridad» (sin explicar cuál) o escríbeme por el [hilo de Twitter](https://x.com/cibernicola_es/status/2116114114686627845), y acordamos cómo contármelo en privado. Si el
repositorio tiene activados los *avisos privados de seguridad* de GitHub (pestaña **Security** ➜
**Report a vulnerability**), mejor aún. Es un proyecto personal: contesto cuando puedo, normalmente en unos días.

## Versiones con soporte

Solo la última versión publicada.
