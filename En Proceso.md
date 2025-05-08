---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
# Proceso de Desarrollo de Soluciones

## 1. Identificación
- Proyecto/FV/Operación identifica la necesidad de negocio

## 2. Asignación de LTF
- Líder Técnico de Flujo (LTF) asignado a la necesidad
  - Levantamiento de Historias de Usuario
  - Creación de Historias de Usuario Técnicas
  - Gestión de Solución con Arquitectura

## 3. Diseño de Solución
- AS (Arquitecto de Solución) diseña junto con LTF
  - Creación del documento HLS
  - Identificación de líneas de producto involucradas

## 4. Líneas de Microservicios
- Si hay líneas de Microservicios, el LTF:
  - Solicita PEP con presupuesto para asignar agente de Fábrica Microservicios
  - Gestiona contextualización técnica del HLS con equipo OSS
  - Gestiona ambientes previos para Desarrollo
  - Gestiona PIPELINEs para despliegue

## 5. Validación de PEP por FÁBRICA DE DESARROLLO
- Validación de presupuesto y estimación
  - Si hay presupuesto y aprobación:
    - Solicita destinación presupuestal sobre PEP para tareas de gestión
    - Asigna Experto de Fábrica a sesión de Contextualización
    - Da viabilidad Técnica del Desarrollo
    - Identifica e Informa Precondiciones Administrativas
    - Define Entregables de Desarrollo
    - Estima esfuerzo de Desarrollo en Alto Nivel
    - Identifica e Informa Precondiciones Técnicas en Alto Nivel
    - Registra Ejecución de Entregables de GESTIÓN

## 6. Validación de Capacidad Técnica por LTF
- LTF valida capacidad para Guías de Integración y gestión de Despliegue
  - Si hay capacidad:
    - Genera Guías de Integración
    - SALTA A NUMERAL 10
  - Si NO hay capacidad:
    - Solicita Estimación de Guías de Integración a FÁBRICA DE DESARROLLO

## 7. Estimación por FÁBRICA DE DESARROLLO
- Estima Gestión Técnica de Guías de Integración
- Estima Gestión de Despliegue

## 8. Validación de Estimación por LTF
- Si Gerente aprueba:
  - Asigna Guías de Integración a FÁBRICA DE DESARROLLO
  - Asigna gestión técnica a FÁBRICA DE DESARROLLO

## 9. Desarrollo por FÁBRICA DE DESARROLLO
- Solicita destinación presupuestal sobre PEP para Guías de Integración
- Asigna Proveedor
- Desarrolla Guías de Integración
- Gestiona PIPELINEs
- Gestiona Ambientes Previos
- Gestiona Pruebas de Carga
- Gestiona Despliegue Productivo
- Gestiona Estimación en Bajo Nivel
- Entrega Guías de Integración a LTF
- Registra Ejecución de Entregables de GESTIÓN
- SALTA A NUMERAL 11

## 10. Desarrollo por LTF
- Desarrolla Guías de Integración
- Gestiona PIPELINEs
- Gestiona Ambientes Previos
- Gestiona Pruebas de Carga
- Gestiona Despliegue Productivo

## 11. Validación y Aprobación por LTF
- Valida y Aprueba Guías de Integración
- Asigna Guías De Integración Desarrolladas a FÁBRICA DE DESARROLLO

## 12. Desarrollo Final por FÁBRICA DE DESARROLLO
- A partir de las guías de integración:
  - Solicita destinación presupuestal sobre PEP Desarrollo Fábrica
  - Asigna Proveedor
  - Despliega en Ambientes Previos
  - Gestiona Documentación del Cambio
  - Realiza Pruebas Unitarias
  - Desarrolla Entregables
  - Gestiona Catálogo Enterprise Architect
  - Concilia Ajustes al Diseño
  - Gestiona Cambio
  - Gestiona Entrega a OSS
  - Registra Ejecución de Entregables de DESARROLLO


# Evolución de Requisitos TORRE DE CONTROL

## [x] 2021 - 2023
- Proyecto
- Gerente del Proyecto
- PEP del Proyecto o Aval de Gerente
- Proveedor
- Costo de la Asignación $
- Recurso Asignado
- Horas

## 2024
### [x] Requisitos Adicionales
- Entregable
- PEP asociado al Entregable
- Evidencia de Entregable (adicional)

## 2025
### Febrero
#### Requisitos Financieros
- Monto Estimado del Entregable
- Proyección de Costo (Estimación)
- Proyección de Proveedor (%Estimación/Proveedor)

### Mayo
#### Requisitos Administrativos
- Programa
- ID de Necesidad
- Nombre de Liberador
  - Se sugiere: Miguel Cajigas, Director de IT
- Centro de Costo
- Pospre / Cuenta
- Grupo de Compras
  - Se identifica: T32
- CTR
  - Se identifica: 8383
- POS CTR
  - Habilitadas: 10 y 140
- POS Contrato Marco
  - Habilitadas: 10 y 140