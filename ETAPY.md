# Śledzenie etapów projektu

Jedno miejsce do aktualizowania postępu zgodnie z kontraktem. Zaznaczaj
zadanie dopiero po wykonaniu i sprawdzeniu; plan lub kod bez wyników nie
oznacza ukończenia etapu.

**Legenda:** `[ ]` do zrobienia · `[x]` wykonane i zweryfikowane  
**Bieżący etap:** do ustalenia z prowadzącym na podstawie harmonogramu.

## Etap 1 — Prezentacja tematu (20%)

**Status: ZALICZONY — 3,0 (55/100; minimum spełnione).**

**Cel zamknięcia:** uzgodniony, wykonalny protokół odtworzenia i eksperymentu
własnego; przygotowane materiały i wyjaśniona podstawa metody.

- [x] Wskazać konkretny wynik, tabelę lub rysunek z publikacji do odtworzenia.
- [x] Oddzielić wierne odtworzenie od eksperymentu własnego/adaptacji.
- [x] Wyjaśnić kluczowe pojęcia i 1–2 wzory lub reguły; zdefiniować symbole
  i pokazać mały przykład obliczeniowy.
- [x] Opisać pytanie i hipotezę, dane i źródło, porównania, metryki,
  podział danych lub generator, parametry, powtórzenia i ochronę przed
  przeciekiem danych.
- [x] Sprawdzić dostęp do danych/kodu i wykonalność krótką próbą.
- [x] Przygotować slajdy, protokół badania (około 1 strony) i informację
  o wykorzystaniu AI.

Uwagi z oceny do wykorzystania w dalszej pracy: teoria i matematyka 13/40,
metodologia 20/35; prowadzący napisał, że zakres merytoryczny i warsztat
matematyczny nie zostały dostatecznie dobrze nakreślone. Te uwagi nie
zmieniają formalnego statusu zaliczenia; należy je uwzględnić w etapie 2.

## Etap 2 — Wstępne wyniki (30%)

**Cel zamknięcia:** działa uzgodniona procedura, są rzeczywiste wyniki
wstępne i potwierdzono rozumienie kluczowych obliczeń.

**Plan pilota:** Ionosphere, Sonar i Glass; po 5 powtórzeń na zbiór.
To wyłącznie wyniki wstępne etapu 2, nie 20 powtórzeń przewidzianych
w notatkach prowadzącego dla naszego projektu. Nie jest to liczba z artykułu:
w §4 Breiman (2001) raportuje 100 powtórzeń dla mniejszych zbiorów.
Raportować pilotaż osobno jako `pilot (n=5)`; nie łączyć z wynikami końcowymi
ani nie przedstawiać jako wykonania pełnego eksperymentu.

**Kontynuacja:** wykonano świeże 20 powtórzeń na tych samych trzech zbiorach,
z nowym ziarnem i osobnymi plikami wynikowymi. Hipoteza poniżej została
sformułowana po obejrzeniu pilotażu, ale przed tym nowym przebiegiem; nie
przypisujemy jej wstecznie do pierwszych pięciu powtórzeń.

- Oczekujemy, że średni błąd OOB `mtry=F` będzie niższy niż `mtry=1`
  w każdym zbiorze.
- Nie oczekujemy, że średni błąd testowy `mtry=F` będzie niższy we wszystkich
  trzech zbiorach; większe `mtry` może zwiększać zarówno siłę, jak i korelację
  drzew.

Wyniki 20 świeżych powtórzeń: obie hipotezy zgodziły się z obserwacjami.
Średni błąd OOB dla `mtry=F` był niższy na każdym zbiorze. Średni błąd testowy
był niższy dla `mtry=F` na Ionosphere i Sonar, ale wyższy na Glass.
Podsumowanie liczbowe jest w README i `results/stage2_fresh20_summary.csv`.

- [x] Uruchomić pilotaż i punkt odniesienia; zapisać zbiory, dokładne indeksy
  podziałów, ziarna, parametry i konfigurację.
- [x] Przygotować tabelę z rzeczywistymi wynikami pilotażu.
- [x] Powiązać obliczenie OOB z kodem, sprawdzić je bezpośrednio względem
  wyniku biblioteki i pokazać przykład liczbowy.
- [x] Wyjaśnić znaczenie `mtry`, zapisać hipotezę przed świeżym przebiegiem
  20 powtórzeń i porównać ją z uzyskanymi wynikami. Hipoteza była
  post-pilotowa, nie przed pierwotnymi pięcioma powtórzeniami.
- [x] Opisać ograniczenia i różnice pilota względem pełnego zakresu:
  użyto trzech zbiorów, bez dodawania cech szumowych; osobny wynik CART nie
  jest artykułowym „One Tree”.
- [ ] Przygotować slajdy, uruchamialny kod, notatkę z postępów
  (około 1–2 stron) i informację o wykorzystaniu AI.

## Etap 3 — Prezentacja i raport końcowy (50%)

**Cel zamknięcia:** komplet uzgodnionych wyników odtworzenia i eksperymentu
własnego, zinterpretowanych i możliwych do sprawdzenia.

- [ ] Wykonać i zachować komplet wyników dla uzgodnionego zakresu; nie usuwać
  wyników niezgodnych z oczekiwaniami.
- [ ] Porównać wyniki z publikacją i jawnie opisać odstępstwa oraz adaptacje.
- [ ] Odpowiedzieć na pytanie badawcze, interpretując wyniki przez teorię,
  założenia, parametry i ograniczenia.
- [ ] Przygotować raport (6–8 stron bez bibliografii i dodatków), slajdy,
  kod, instrukcję uruchomienia, zależności i ich wersje, konfiguracje,
  surowe wyniki oraz informację o wykorzystaniu AI.
- [ ] Sprawdzić, że wybrany wynik można odtworzyć z przekazanych materiałów.

## Zasada aktualizacji zakresu

Istotna zmiana danych, metryki, zakresu odtworzenia lub eksperymentu własnego
wymaga uzgodnienia z prowadzącym i odnotowania w protokole. Wcześniejsza
wersja pracy z innego folderu nie jest automatycznie uznawana za ukończenie
zadań na tej liście — najpierw należy ją zweryfikować względem uzgodnionego
zakresu.
