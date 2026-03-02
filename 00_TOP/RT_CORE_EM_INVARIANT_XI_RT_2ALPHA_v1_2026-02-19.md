# RT Core — EM-invariant Ξ_RT (”2α”, två-kantsmåttet) — v1 (2026-02-19)

Syfte: ge en **Core-intern** definition av den dimensionlösa EM-invarianten som i Overlay jämförs mot finstrukturkonstanten.

> Core-regel: inga SI-tal/konstanter används som indata. All jämförelse mot α sker i Overlay.

---

## 1) Definition (Core)

Vi definierar två Core-objekt på RP-skärmen Σ (mät- / boundary-vy):

**D1. RT-karaktäristisk impedans (Z0_RT).**  
Ett dimensionslöst impedansmått som kodar hur Σ kopplar **E- och B-dualerna** (”våg-karaktären”) för en given normalisering av TickPulse och RP-strobe.

**D2. RT-grundkonduktans (G0_RT).**  
Ett dimensionslöst transportkvantum för **en enda helikal kanal** (AB- / spin-resolvad kanal) i den diskreta C30-geometrin.

**D3. EM-invariant (två-kantsmåttet).**  
\[
\Xi_{RT}\;:=\;Z0_{RT}\,G0_{RT}.
\]

I vår notation används namnet **”2α”** för \(\Xi_{RT}\) när vi talar om jämförelsen mot etablerad fysik, men **själva talet** är ett Core-utfall.

---

## 2) Varför ”halva vågen” (faktor 2 och 4)

Den klassiska faktor-2 som dyker upp i diskussionen handlar om **hur många kanaler** mätkedjan faktiskt ser:

- **En kanal (spin/helicitets-resolvad, en helix):** \(Z0_{RT}\,G0_{RT}=\Xi_{RT}\)  (”halva vågen” i vardagsspråk)
- **Två kanaler (båda spin/heliciteter):** \(Z0_{RT}\,(2G0_{RT})=2\,\Xi_{RT}\)

Det här är inte en efterhandsförklaring: det är en **normaliseringsfråga** (”en kanal” vs ”dublett”) som måste anges i varje jämförelse.

---

## 3) Tre oberoende Core-spår (status: definition PASS, härledning pågår)

Historiskt har \(\Xi_{RT}\) dykt upp som samma invariant via tre spår:

1) **Impedans/transport-spåret:** direkt via produkten \(Z0_{RT}G0_{RT}\).  
2) **AB-slinga (native helix):** \(\Xi_{RT}=1/\Lambda_{AB}\) i RT-enheter (c=1), där \(\Lambda_{AB}\) är ett rent geometri-/orienteringsmått för A/B-slingan.  
3) **Tick-spåret:** en sluten integral/medel över C30-geometrin ger ett rent geometri-tal för \(\Lambda_{AB}\) (i tidiga approximationer nära en \(\pi^2\)-faktor; t.ex. ~\(12\pi^2\) som mål att härleda, inte anta).

**Viktig statusrad:** I V7 är detta ännu **inte uppgraderat till Core-PASS som tal** (dvs en pipeline som räknar fram \(\Xi_{RT}\) utan Overlay-stöd). Därför behandlas \(\Xi_{RT}\) här som Core-definition + pågående härledning.

---

## 4) Overlay-jämförelse (endast kontroll, ej input)

För jämförelse i Overlay kopplas \(\Xi_{RT}\) till den etablerade finstrukturkonstanten via standard-EM/transportidentiteter.  
Detta får aldrig påverka Core-val (D-5 / no-rescale).

