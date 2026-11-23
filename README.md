# random-forest-oob

Projekt dotyczy oceny błędu out-of-bag (OOB) i odporności lasów losowych na
cechy nieinformacyjne, na podstawie Breiman (2001). Status zadań i etapy
opisuje [ETAPY.md](ETAPY.md).

## Pilotaż etapu 2 — pierwsze 5 powtórzeń

Pierwsze 5 powtórzeń dla trzech zbiorów stanowiło pilotaż. Przed kolejnymi
nowymi obliczeniami zapisano hipotezę w sekcji poniżej. Skrypt wykonuje świeży
przebieg 20 powtórzeń dla każdego zbioru, z nowym ziarnem, i zapisuje wyniki
osobno — nie nadpisuje pierwotnego pilotażu:

```powershell
python .\stage2_pilot.py
```

Skrypt sprawdza sumy SHA-256 archiwów w `data/raw/`, a następnie wykonuje
20 nowych powtórzeń losowego podziału 90/10 dla każdego ze zbiorów Ionosphere,
Sonar i Glass. W każdym podziale porównuje lasy z `mtry=1` oraz
`mtry=int(log2(M)+1)` (odpowiednio 6, 6 i 4), wybiera wariant z mniejszym
błędem OOB na zbiorze treningowym i ocenia oba warianty na tym samym zbiorze
testowym. Punkt odniesienia CART jest trenowany na tym samym podziale.
Podziały są nieustratyfikowane, zgodnie z przyjętym protokołem.

Wyniki są ułamkami błędnych klasyfikacji (np. `0.05` oznacza 5%). Poniższe
wartości to średnie z **pierwszych pięciu powtórzeń pilota**, zaokrąglone do
0,1 punktu procentowego:

| Zbiór | M | F | OOB mtry=1 | OOB mtry=F | Test: mtry=1 | Test: wybór OOB | Test: CART |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ionosphere | 34 | 6 | 7,2% | 6,9% | 5,0% | 5,0% | 8,9% |
| Sonar | 60 | 6 | 19,4% | 18,0% | 19,0% | 21,0% | 25,7% |
| Glass | 9 | 4 | 22,6% | 22,3% | 24,5% | 25,5% | 35,5% |

W tym pilotażu średni błąd OOB dla `mtry=F` był nieco niższy na każdym
zbiorze, ale wybór na podstawie OOB nie zawsze dawał najniższy błąd testowy.
Wyższe `mtry` oznacza więcej kandydatów przy podziale węzła; jego wpływ na
wynik zależy od równowagi między siłą drzew i ich korelacją. Pięć powtórzeń
jest za małą próbą, by traktować te różnice jako wnioski końcowe.

### Hipoteza przed świeżym przebiegiem 20 powtórzeń

Pierwsze pięć powtórzeń było już obejrzane. Hipoteza poniżej została
sformułowana po pilotażu, ale przed świeżym przebiegiem 20 nowych podziałów;
nie przypisujemy jej wstecznie do pierwotnego pilotażu:

- średni błąd OOB dla `mtry=F` będzie niższy niż dla `mtry=1` na każdym z
  trzech zbiorów;
- średni błąd testowy dla `mtry=F` nie będzie niższy na wszystkich trzech
  zbiorach.

Większe `mtry` dopuszcza więcej cech przy szukaniu podziału, co może zwiększyć
siłę drzew, ale może też zwiększyć ich korelację. Dlatego nie zakładamy
jednakowej poprawy błędu testowego.

### Wyniki świeżego przebiegu (20 powtórzeń)

W świeżym przebiegu średni błąd OOB dla `mtry=F` był niższy na wszystkich
trzech zbiorach. Błąd testowy dla `mtry=F` był niższy na Ionosphere i Sonar,
ale wyższy na Glass. Obie zapisane prognozy zgadzają się więc z obserwowanym
wzorcem; jest to opisowy wynik na tych zbiorach, nie test istotności.

| Zbiór | M | F | OOB mtry=1 | OOB mtry=F | Test mtry=1 | Test mtry=F | Test wybór OOB | Test CART |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Ionosphere | 34 | 6 | 7,13% | 6,62% | 5,97% | 5,56% | 5,83% | 10,56% |
| Sonar | 60 | 6 | 19,52% | 17,94% | 18,57% | 15,24% | 16,67% | 30,24% |
| Glass | 9 | 4 | 23,10% | 22,55% | 22,27% | 25,45% | 24,09% | 32,05% |

Wyniki są średnimi błędami z 20 świeżych podziałów 90/10. Zgodność z
przewidywaniem nie oznacza, że `mtry=F` zawsze będzie lepsze; w szczególności
wynik testowy Glass pokazuje przeciwny kierunek.

Przykład rachunku OOB: dla 315 obserwacji treningowych prawdopodobieństwo,
że pojedyncza obserwacja nie znajdzie się w próbce bootstrapowej, wynosi
`(1 - 1/315)^315 ≈ 0,3673`. Przy 100 drzewach daje to średnio około 36,73
głosów OOB na obserwację. Skrypt dodatkowo oblicza błąd OOB bezpośrednio
z głosów w `oob_decision_function_` i sprawdza jego zgodność z
`1 - oob_score_`.

### Zakres i ograniczenia

- Pierwsze wyniki to **pilotaż: 3 zbiory × 5 powtórzeń**. Świeży przebieg
  20 powtórzeń na tych samych trzech zbiorach nie jest pełnym odtworzeniem
  artykułu. Dwadzieścia powtórzeń to zakres projektu z notatek prowadzącego,
  nie liczba z artykułu Breimana, który w §4 opisuje 100 powtórzeń dla
  mniejszych zbiorów.
- Testowane zbiory są podzbiorem danych użytych w artykule. Pilotaż nie
  obejmuje jeszcze pełnego zakresu danych ani eksperymentu z dodanymi
  cechami szumowymi.
- CART jest osobnym punktem odniesienia w tym pilotażu; nie należy utożsamiać
  jego błędu testowego z artykułowym wynikiem „One Tree”, który jest oparty
  na błędach OOB pojedynczych drzew z lasu.
- Wyniki nie uzasadniają jeszcze wyboru ostatecznych parametrów ani
  uogólnienia na inne zbiory.

### Artefakty i odtwarzalność

Skrypt zapisuje ten przebieg do osobnych plików:

- `results/stage2_fresh20_runs.csv` — wszystkie 20 powtórzeń na zbiór,
  wraz z podziałami, indeksami obserwacji, ziarnami, metrykami i czasami;
- `results/stage2_fresh20_summary.csv` — podsumowanie wszystkich 20;
- `results/stage2_fresh20_metadata.json` — konfigurację, wersje bibliotek,
  sumy kontrolne danych i zapisaną hipotezę.

Konfiguracja używa 100 drzew na las, bazowego ziarna `20261123` (wybranego
przed przebiegiem dla odróżnienia nowej sekwencji; bez znaczenia naukowego)
i ustalonych ziaren dla każdego podziału/modelu. Świeży przebieg wykonał 180
dopasowań; pierwotny pilotaż zachowano osobno.
Przy pierwszym uruchomieniu użyto Python 3.12.5, NumPy 2.3.4, pandas 2.3.3
i scikit-learn 1.7.2. Żaden z tych przebiegów nie jest pełnym odtworzeniem
całego zakresu artykułu.
