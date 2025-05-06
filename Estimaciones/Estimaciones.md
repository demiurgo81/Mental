---
title: Inicio Flujo Gestión Estimaciones
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---

## Nueva Estimacion + PEP
###
| accion | tabla | campo | valor |
|-|-|-|-|
| `insert` | DF_ESTIMACION | ID_ESTIMACION | *NEW*  |
| `update` | DF_ESTIMACION | ESTADO_ESTIMACION | "PENDIENTE" |
### [x] **Validad PEP**
#### [**Existe ID_PEP**](estadoPEP.html)
#### **No Existe ID_PEP en DF_PEP**
##### 
| accion | tabla | campo | valor |
|-|-|-|-|
| `insert` | DF_PEP| DF_PEP | ID_PEP | *PEP* |
| `update` | DF_PEP| ESTADO_PEP | "NUEVO" |
##### [INICIO](Index.html)
## [**Consultar Estimación + PEP**](estadoPEP.html)

---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
  
---

# [Validar Estado PEP](Index.html)
## **NUEVO**
### ==**ADV**: *"PEP [ID_PEP] existe,  estado no aprobado (NUEVO)"*==
### [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)
## **APROBADO**
### **Validar Estado Estimacion**
#### [x] **Estimacion PENDIENTE**
##### ==**ADV:** *"Estimación [ID_ESTIMACION] esta PENDIENTE de aprobación y restringe ejecucion"*==
##### [**INICIO**](Index.html)
#### [x] **Estimacion APROBADA o CERRADA**
##### **Validar Solped**
###### [x] [**Solped EXISTE**](estadoSolped.html)
###### [x] [**Solped NO Existe**](estadoEjecucion.html)
## **RECHAZADO** 
### ==**ADV:** *"PEP [ID_PEP] aparece RECHAZADO actualmente"*==
### **Validar Solped**
#### [x] [**Solped EXISTE**](estadoSolped.html)
#### [x] **Solped NO Existe**
##### ==**ADV:** *"La estimacion [ID_ESTIMACION] por  $ESTIMADO no tiene Solped Asociada, no puede ejecutar"*==
##### [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)


---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---

# [Validar Estado Solped](estadoPEP.html)
## **CREADA**
### **MSG:** *"`SOLPED [ID_SOLPED] CREADA (Valor: $ESTIMADO), pendiente de gestion, OC por [Area]. Ejecucion actual: $EJECUCION`"*
### [**Validar Ejecucion/Estimacion**](estadoEjecucion.html)
## **FINALIZADA** 
### [x] **Validar OC**
##### **No Existe OC**
###### ==**ADV:** *"SOLPED [ID_SOLPED] FINALIZADA sin OC asociada, pendiente OC por [Area]. Ejec: $EJECUCION"*==
###### [**Validar Ejecucion/Estimacion**](estadoEjecucion.html)
##### [**OC CREADA**](estadoEjecucion.html)
##### **OC FINALIZADA**
###### ==**ADV:** *"LA OC [ID_OC] esta FINALIZADA, se han ejecutado [$EJECUCION] de [$ESTIMADO] estimados."*==
###### [**Validar Ejecucion/Estimacion**](estadoEjecucion.html)

---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
# [**Validar Estado Ejecucion**](estadoSolped.html)
## [x] **$EJECUCION <= $ESTIMADO (Sub-ejecución)** 
### [x] **¿Existe OC?**
#### **MSG:** -> *"`La OC [ID_OC] asociada a la estimacion [ID_ESTIMACION] por valor: $ESTIMADO, esta activa y en gestion por [Area]. Ejecucion actual: $EJECUCION`"*
### [x] **¿Existe Solped?**
#### **MSG:** *"`SOLPED [ID_SOLPED] asociada a la estimacion [ID_ESTIMACION] por valor: $ESTIMADO), esta pendiente de gestion, OC por [Area]. Ejecucion actual: $EJECUCION`"*
### [x] **Sin Solped**
#### **MSG:** *"`La estimacion [ID_ESTIMACION] por valor: $ESTIMADO, esta pendiente de gestion, SOLPED por [Area]. Ejecucion actual: $EJECUCION`"*
### [**INICIO**](Index.html)

## [x] **$EJECUCION > $ESTIMADO (Sobre-ejecución)**
### ==**ADV:** *"La estimacion [ID_ESTIMACION] por valor: $ESTIMADO, presenta una sobreejecucion por $ESTIMADO - $EJECUCION, la ejecucion sera restringida y la estimacion sera RESTRINGIDA urgente gestion por [Area]"*==
###
| accion | tabla | campo | valor |
|-|-|-|-|
| `insert` | DF_EST_ALERTA| TIPO_ALERTA... | *"BLOQUEAR"*,ID_ESTIMACION,ID_SOLPED,ID_OC,ID_PEP |


### [**BLOQUEAR EJECUCION CRONOS**](bloqueoEjecucion.html)

---
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 1
---
# [**BLOQUEO EJECUCION CHRONOS**](Index.html)
## ==**ADV:** *"La estimacion [ID_ESTIMACION] por valor: $ESTIMADO, sera bloqueada hasta que la sobre ejecucion por $ESTIMADO-$EJECUTADO sean cargados a un presupuesto diferente o se elimine."*==
##
| accion | tabla | campo | valor |
|-|-|-|-|
| `update` | DF_ESTIMACION | ESTADO_ESTIMACION | "PENDIENTE" |
## [x] **$EJECUCION > $ESTIMADO (Sobre-ejecución)**
###
| accion | tabla | campo | valor |
|-|-|-|-|
| `update` | DF_EST_ALERTA | SOBRECOSTO | $ESTIMADO-$EJECUTADO |
## [**INICIO**](Index.html)


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