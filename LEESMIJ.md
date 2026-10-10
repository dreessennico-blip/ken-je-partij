# Hoe goed ken jij je partij? - automatische update

Dit project werkt de app elke nacht bij met nieuwe moties van de Tweede Kamer.

## Wat zit erin
- `docs/index.html` - de app zelf (dit is de website).
- `bijwerken.py` - het programma dat nieuwe moties ophaalt, controleert en toevoegt.
- `controle.js` - controleert de app voordat een wijziging wordt opgeslagen. Gaat er iets mis, dan blijft de oude versie staan.
- `.github/workflows/nachtelijke-update.yml` - de planning: elke nacht om 02:30 UTC.
- `verslag-laatste-run.md` - na elke run: wat is toegevoegd, wat is weggelaten en waarom.

## Eenmalig instellen (ongeveer een kwartier)
1. Maak een gratis account op github.com.
2. Klik rechtsboven op **+** en kies **New repository**. Geef het een naam, zet **Public** aan en klik **Create repository**.
3. Klik op **uploading an existing file** en sleep deze bestanden erin: `bijwerken.py`, `controle.js`, `LEESMIJ.md` en de map `docs`. Klik op **Commit changes**.
4. Het planningsbestand moet in een verborgen map staan. Klik op **Add file > Create new file**. Typ bij de naam precies `.github/workflows/nachtelijke-update.yml` (de schuine strepen maken de mappen vanzelf). Plak de inhoud van het bestand `nachtelijke-update.yml` en klik op **Commit changes**.
5. Ga naar **Settings > Actions > General**, scrol naar **Workflow permissions**, kies **Read and write permissions** en klik op **Save**.
6. Ga naar **Settings > Pages**. Kies bij **Branch** de optie `main` en de map `/docs`, en klik op **Save**. Na een paar minuten staat de app op het adres dat daar verschijnt.

## De eerste test
1. Ga naar het tabblad **Actions**, kies **Nachtelijke update** en klik op **Run workflow**.
2. Na een paar minuten staat er een groen vinkje (gelukt) of een rood kruis (mislukt).
3. Open `verslag-laatste-run.md` voor wat er is gebeurd. Bij een rood kruis: klik op de run en kopieer de rode regels naar mij.

## Wat je in het verslag moet nalopen
- **Weggelaten moties:** die zijn niet in de app gekomen, en het verslag zegt waarom.
- **Nieuwe dossiers zonder ministerie:** die staan onder "Overig" tot ze zijn ingedeeld.
- **Mislukte dagen:** de volgende nacht wordt het opnieuw geprobeerd.

## Goed om te weten
- Na nieuwe verkiezingen of een fractiewijziging komt er een fractie bij of weg. Het programma weigert dan moties met andere fracties dan de app kent. De app moet dan eerst worden aangepast.
- GitHub kan geplande taken pauzeren als er lang niets gebeurt. Zie je dat het verslag niet meer wordt bijgewerkt, ga dan naar Actions en zet de taak weer aan.
- Het programma is alleen offline getest, met de gegevens van de afgelopen maanden. De eerste echte nacht is dus ook de eerste echte test met het internet.
