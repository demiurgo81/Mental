---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---

# Gestión Estimaciones
## Relacionar Estimacion + PEP
### [**Existe ID_PEP en DF_PEP**](estadoPEP.html)
### **No Existe ID_PEP en DF_PEP**
#### 1. Insertar registro en DF_PEP / DF_INICIATIVA
#### 2. ESTADO_PEP = 'NUEVO'
##### [INICIO](index.html)
## [**Consultar Estimación + PEP**](estadoPEP.html)


ESTADOPEP
---
title: ESTADO PEP
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
## **NUEVO**
### ADV: "PEP [ID] existe,  estado no aprobado (NUEVO)"
#### [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)
## [**APROBADO**](estadoEstimacion.html)
## **RECHAZADO** 
### ADV: PEP [ID] está RECHAZADO"
#### [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)


---
title: ESTADO ESTIMACION
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
## **PENDIENTE**
	- ADV: "Estimación [ID] PENDIENTE de aprobación"
		- [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)
## [**APROBADA / CERRADA**](estadoSolped.html)


---
title: ESTADO SOLPED
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
## **No Existe**
### ADV: "No se ha creado SOLPED por $ESTIMACION para Est. [ID]. Pendiente [Area]."
#### [Ejecucion/Estimacion](estadoEjecucion.html)
## **CREADA**
### MSG: "SOLPED [ID] CREADA (Valor: $ESTIMACION), pendiente OC por [Area]. Ejec: $EJECUCION"
#### [Ejecucion/Estimacion](estadoEjecucion.html)
## **FINALIZADA** 
### [Validar OC](estadoOC.html)


---
title: ESTADO OC
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
## **No Existe OC**
### ADV: "SOLPED [ID] FINALIZADA sin OC asociada, pendiente OC por [Area]. Ejec: $EJECUCION"
#### [Ejecucion/Estimacion](estadoEjecucion.html)
## [**OC CREADA**](estadoEjecucion.html)
## [**OC FINALIZADA**](estadoEjecucion.html)
## **OC ALERTADA**
	- ADV: "OC [ID] ya ALERTADA por sobre-ejecución. Ejec: $EJECUCION vs Est: $ESTIMACION. Pendiente [Area]."
		- [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)

---
title: BLOQUEO EJECUCION
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
##


## 5. Crear PEP
   - Insertar registro en DF_PEP / DF_INICIATIVA
## 6. Actualizar Estado PEP
   - ESTADO_PEP = 'NUEVO'
   - -> INICIO (Esperar Aprobación)
## 8. ADV: Estimación Pendiente
   - "Estimación [ID] PENDIENTE de aprobación"
   - -> INICIO
## 9. Validar SOLPED (por ID_PEP + ID_EST)
   - **Existe** -> 10. Validar Estado SOLPED
   - **No Existe** -> 19. ADV: SOLPED Inexistente
## 10. Validar Estado SOLPED
    - **CREADA** -> 11. MSG: SOLPED Creada
    - **FINALIZADA** -> 12. Validar OC
    - **Otro** -> ADV: Estado SOLPED inesperado -> INICIO
## 11. MSG: SOLPED Creada
    - "SOLPED [ID] CREADA (Valor: $E), pendiente OC por [Area]. Ejec: $J"
    - -> INICIO (Esperar Finalización SOLPED/Creación OC)

## 12. Validar OC (asociada a SOLPED)
    - **No Existe OC** -> 13. ADV: SOLPED sin OC
    - **OC CREADA** -> 14. MSG: OC Creada
    - **OC FINALIZADA** -> 15. Validar Ejecución vs Estimación
    - **OC ALERTADA** -> 16. ADV: OC ya Alertada
    - **Otro Estado OC** -> ADV: Estado OC inesperado -> INICIO

## 13. ADV: SOLPED sin OC
    - "SOLPED [ID] FINALIZADA sin OC asociada. Revisar."
    - -> INICIO

## 14. MSG: OC Creada
    - "OC [ID] CREADA. SOLPED [ID] Finalizada. Pendiente Finalización OC por [Area]. Est: $E, Ejec: $J"
    - -> INICIO (Esperar Finalización OC)

## 15. Validar Ejecución ($J) vs Estimación ($E)
    - **$J < $E (Sub-ejecución)** -> 17. ADV: Sub-ejecución
    - **$J == $E (Ejecución Exacta)** -> 18. MSG: Ejecución Exacta
    - **$J > $E (Sobre-ejecución)** -> 21. ADV: Sobre-ejecución

## 16. ADV: OC ya Alertada
    - "OC [ID] ya ALERTADA por sobre-ejecución previa. Ejec: $J vs Est: $E. Pendiente [Area]."
    - -> INICIO

## 17. ADV: Sub-ejecución
    - "OC [ID] FINALIZADA con sub-ejecución ($E - $J). Revisar [Area]."
    - -> 20. Cerrar Estimación (Sub-ejec.)

## 18. MSG: Ejecución Exacta
    - "OC [ID] FINALIZADA. Presupuesto ($E) ejecutado ($J)."
    - -> 20. Cerrar Estimación (Exacta)

## 19. ADV: SOLPED Inexistente
    - "No se ha creado SOLPED por $E para Est. [ID]. Pendiente [Area]."
    - -> INICIO

## 20. Cerrar Estimación
    - ACTUALIZAR ESTADO_ESTIMACION = 'CERRADA'
    - **Desde 17 (Sub-ejec.)** -> 20b. MSG: Cierre con Sub-ejec. -> FIN
    - **Desde 18 (Exacta)** -> 20c. MSG: Cierre con Ejec. Completa -> FIN

## 21. ADV: Sobre-ejecución
    - "¡SOBRE-EJECUCIÓN! OC [ID] Finalizada. Excedente ($J - $E). Urgente [Area]."
    - -> 22. Alertar OC

## 22. Alertar OC
    - ACTUALIZAR ESTADO_OC = 'ALERTADA'
    - -> 23. Cerrar Estimación (Sobre-ejec.)

## 23. Cerrar Estimación (Sobre-ejec.)
    - ACTUALIZAR ESTADO_ESTIMACION = 'CERRADA'
    - -> 24. MSG: Cierre con Alerta

## 24. MSG: Cierre con Alerta
    - "Estimación [ID] CERRADA. OC [ID] ALERTADA por sobre-ejecución."
    - -> FIN