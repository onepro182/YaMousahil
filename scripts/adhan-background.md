# Test — Alerte d'adhan YaMousahil (navigateur fermé / téléphone verrouillé)

## Ce qui a été livré

| Plateforme | Mécanisme | Fonctionne si… |
|---|---|---|
| Windows (ce PC, via navigateur) | `Notification` + overlay in-page + tâche planifiée | voir ci-dessous |
| Windows (tâche planifiée) | `adhan-windows.ps1` — toast + adhan via Task Scheduler **sans navigateur** | session ouverte (même verrouillée), notifications autorisées |
| Android (APK v1.1.0) | `AlarmManager.setAlarmClock` + notification plein écran + adhan embarqué | app fermée, écran verrouillé, téléphone allumé |

**Limites honnêtes :**
- Téléphone **éteint** : impossible pour toute application (rien ne tourne). Au rallumage, les alarmes du jour se reprogramment via `BootReceiver`.
- Web (sans APK) : aucun toast possible si le navigateur est totalement arrêté. Seule la tâche Windows couvre ce cas sur PC.
- Android 14+ : l'écran plein sur l'écran verrouillé dépend de la permission « Notifications plein écran » (activée par défaut pour une appli d'alarme comme celle-ci).

## Test A — Dans le navigateur (PC 1 et PC 2)

1. Ouvrir `http://localhost:8765/?testAlert=1` (PC 1, serveur `node serve.js` déjà lancé) ou le site déployé `https://onepro182.github.io/YaMousahil/?testAlert=1` (les 2 PC).
2. Menu ⚙ → صلاة / الأذان → **اختبار شاشة التنبيه** : l'overlay « حان الآن موعد صلاة العشاء » doit s'afficher + notification Windows (si autorisées).
3. Accepter la permission de notification au premier essai.

> ⚠ Si l'alerte n'apparaît pas : vérifier les notifications de Windows (Paramètres → Système → Notifications), et le « Assistance à la mise au point » (Focus) désactivé.

## Test B — Navigateur FERMÉ, PC verrouillé (PC 1 : installé, PC 2 : à installer)

Tâche planifiée `YaMousahil-Adhan` : exécute un contrôle chaque minute, indépendamment de tout navigateur.

Sur **ce PC (LEOPARD)** : déjà installée et en cache. Test immédiat (toast + 25 s d'adhan) :

```powershell
cd C:\Users\Admin\Desktop\APK\APP_web
powershell -ExecutionPolicy Bypass -File scripts\adhan-windows.ps1 -Action Test
```
Prochaines vraies alertes aujourd'hui (14/11/2026) : **Maghrib 17:08**, **Isha 18:25**.

Sur le **second PC Windows** :
1. Copier le dossier `APP_web` (ou au minimum `scripts\adhan-windows.ps1`, `assets\audio\adhan-azan1.mp3`, `Logo.png`).
2. Depuis ce dossier : `powershell -ExecutionPolicy Bypass -File scripts\adhan-windows.ps1 -Action Install`
3. Tester : `… -Action Test`. Désinstaller : `… -Action Uninstall`.
4. Trouver la ville dans `ShowTimes` (doit afficher les horaires Oujda, méthode 21 Habous).

État : `schtasks /query /tn YaMousahil-Adhan` ; cache local : `%LOCALAPPDATA%\YaMousahil\`.

## Test C — Téléphone Android (APK YaMousahil-v1.1.0.apk)

L'APK **ne peut** afficher d'alerte app fermée que si le site hébergé synchronise les heures (déploiement GitHub Pages requis).

1. Activer les options développeur → **Débogage sans fil** (Android 11+ : « Couplage avec code ») puis recueillir IP:port.
2. PC : `adb pair <IP>:<port-couplage>` puis `adb connect <IP>:5555` (ou simplement brancher en USB et valider le dialogue).
3. Installer : `adb install -r "C:\Users\Admin\Desktop\APK\YaMousahil-v1.1.0.apk"`
4. Ouvrir YaMousahil → ⚙ → الأذان :
   - activer **الأذان التلقائي**, sauvegarder ;
   - presser **اختبار إشعار الخلفية (اقفل الهاتف — خلال 15 ثانية)** ;
   - verrouiller immédiatement l'écran : au bout de ~15 s, la notification « حان الآن موعد صلاة العشاء » doit apparaître SUR L'ÉCRAN DE VERROUILLAGE avec l'adhan, **même si l'app est fermée** (la fermer avant de verrouiller pour le test dur).
5. Le même mécanisme s'arme pour les 5 prières du jour + lendemain (désactivation : décocher l'adhan et sauvegarder).

### Android — points de vigilance
- Premier lancement : accepter la permission **Notifications** (Android 13+).
- Écran plein verrouillé : Android 14+ → Paramètres → Apps → YaMousahil → **Notifications plein écran** (ON).
- Économie de batterie : pour ce constructeur, exclure YaMousahil des optimisations si l'alerte d'arrière-plan n'arrive pas (Samsung : Battery → services sans arrière-plan restreints).
- Après redémarrage du téléphone : alarmes ré-armées automatiquement (BootReceiver).

## État de la vérification (14/11/2026, 15:30)
- Build APK v1.1.0 OK ; `assembleRelease` signé (keystore existant).
- Toast + adhan Windows : **test OK** (notification affichée, adhan joué).
- Tâche `YaMousahil-Adhan` : **enregistrée**, prochaine exécution planifiée chaque minute.
- Affichage horaires Oujda : **OK** (API aladhan, méthode 21).
- Web (JS) : syntaxe OK ; overlay `?testAlert=1` à confirmer visuellement dans le navigateur (extension de pilotage déconnectée lors du test).
- Téléphone : **en attente** d'un téléphone joignable (adb) pour l'installation — voir Test C.
