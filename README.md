# IRRIGO 🌱
## Plataforma Web para Automatizar Riegos

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compatible-blue.svg)](https://www.docker.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.0-purple.svg)](https://getbootstrap.com/)
[![Chart.js](https://img.shields.io/badge/Chart.js-Interactive%20Charts-orange.svg)](https://www.chartjs.org/)

---

## Descripción del Proyecto

IRRIGO es un sistema de riego agrícola automatizado que optimiza el uso del agua mediante el monitoreo inteligente de la humedad del suelo. La plataforma permite programar horarios de riego, visualizar datos en tiempo real y alternar entre modos de control manual y automático.

## Características Principales

- **Automatización inteligente** - Riego basado en sensores de humedad
- **Visualización de datos** - Gráficos interactivos con Chart.js
- **Programación de horarios** - Control temporal del sistema de riego
- **Doble modo de control** - Manual y automático
- **Interfaz web responsive** - Diseñada con Bootstrap
- **Panel de administración** - Gestión completa del sistema
- **Deployment en la nube** - Containerizado con Docker

## Tecnologías Utilizadas

### Frontend
- **Bootstrap** - Framework CSS para diseño responsive
- **Chart.js** - Librería para gráficos interactivos
- **HTML5/CSS3/JavaScript** - Tecnologías web estándar

### Backend
- **API REST** - Comunicación con sensores via JSON
- **Base de datos** - Almacenamiento de datos de sensores y configuraciones

### DevOps
- **Docker** - Containerización y deployment
- **Cloud Deployment** - Hosting en servicios cloud

## Funcionalidades

### Panel Principal
- Monitoreo en tiempo real de la humedad del suelo
- Gráficos de tendencias históricas
- Estado actual del sistema de riego

### Panel de Control
- Activación/desactivación manual del riego
- Programación de horarios automáticos
- Configuración de umbrales de humedad

### Panel de Administración (Solo Admin)
- Gestión de usuarios y permisos
- Configuración avanzada del sistema
- Mantenimiento y logs del sistema



## Casos de Uso

1. **Agricultor supervisa cultivos remotamente**
   - Acceso via web desde cualquier dispositivo
   - Notificaciones de niveles críticos de humedad

2. **Riego programado automático**
   - Sistema riega según horarios preestablecidos
   - Ajustes automáticos basados en datos de sensores

3. **Administrador gestiona el sistema**
   - Control total sobre configuraciones
   - Monitoreo de rendimiento y mantenimiento


## Instalación

### Prerrequisitos
- Docker y Docker Compose
- Node.js (para desarrollo local)
- Sensores de humedad compatibles

### Instalación con Docker

1. **Clonar el repositorio**
```bash
git clone https://github.com/NoeParedes/cognitive.git
cd cognitive
```

2. **Construir y ejecutar con Docker**
```bash
docker-compose up --build
```

3. **Acceder a la aplicación**
```
http://localhost:3000
```

### Instalación para Desarrollo Local

1. **Instalar dependencias**
```bash
npm install
```

2. **Configurar variables de entorno**
```bash
cp .env.example .env
```

3. **Ejecutar en modo desarrollo**
```bash
npm start
```

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.
