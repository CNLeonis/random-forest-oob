# random-forest-oob

Projekt dotyczy oceny błędu out-of-bag (OOB) i odporności lasów losowych na
cechy nieinformacyjne, na podstawie Breiman (2001). Status zadań i etapy
opisuje [ETAPY.md](ETAPY.md).

## Pilotaż etapu 2

Uruchomienie z katalogu repozytorium:

```powershell
python .\stage2_pilot.py
```

Skrypt sprawdza sumy SHA-256 archiwów w `data/raw/`, a następnie wykonuje
pięć powtórzeń losowego podziału 90/10 dla każdego ze zbiorów Ionosphere,
Sonar i Glass. W każdym podziale porównuje lasy z `mtry=1` oraz
`mtry=int(log2(M)+1)` (odpowiednio 6, 6 i 4), wybiera wariant z mniejszym
błędem OOB na zbiorze treningowym i ocenia oba warianty na tym samym zbiorze
testowym. Punkt odniesienia CART jest trenowany na tym samym podziale.
Podziały są nieustratyfikowane, zgodnie z przyjętym protokołem.

Wyniki są ułamkami błędnych klasyfikacji (np. `0.05` oznacza 5%). Poniższe
wartości to średnie z **pięciu powtórzeń pilota**, zaokrąglone do 0,1 punktu
procentowego:

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

Przykład rachunku OOB: dla 315 obserwacji treningowych prawdopodobieństwo,
że pojedyncza obserwacja nie znajdzie się w próbce bootstrapowej, wynosi
`(1 - 1/315)^315 ≈ 0,3673`. Przy 100 drzewach daje to średnio około 36,73
głosów OOB na obserwację. Skrypt dodatkowo oblicza błąd OOB bezpośrednio
z głosów w `oob_decision_function_` i sprawdza jego zgodność z
`1 - oob_score_`.

### Zakres i ograniczenia

- To **wstępny pilotaż: 3 zbiory × 5 powtórzeń**, a nie 20 powtórzeń
  przewidzianych w notatkach prowadzącego dla naszego projektu ani pełne
  odtworzenie wyników artykułu. Te 20 powtórzeń to zakres projektu, nie liczba
  z artykułu Breimana: w §4 artykułu małe zbiory analizowano w 100 powtórzeniach.
- Testowane zbiory są podzbiorem danych użytych w artykule. Pilotaż nie
  obejmuje jeszcze pełnego zakresu danych ani eksperymentu z dodanymi
  cechami szumowymi.
- CART jest osobnym punktem odniesienia w tym pilotażu; nie należy utożsamiać
  jego błędu testowego z artykułowym wynikiem „One Tree”, który jest oparty
  na błędach OOB pojedynczych drzew z lasu.
- Wyniki nie uzasadniają jeszcze wyboru ostatecznych parametrów ani
  uogólnienia na inne zbiory.

### Artefakty i odtwarzalność

Skrypt zapisuje:

- `results/stage2_pilot_runs.csv` — 15 wierszy z podziałami, indeksami
  obserwacji, ziarnami, metrykami i czasami dopasowania;
- `results/stage2_pilot_summary.csv` — średnie i odchylenia standardowe
  błędów dla każdego zbioru;
- `results/stage2_pilot_metadata.json` — konfigurację, wersje bibliotek,
  sumy kontrolne danych i jawne oznaczenie pilotażu.

Konfiguracja używa 100 drzew na las, bazowego ziarna `20261026` i ustalonych
ziaren dla każdego podziału/modelu. Przy pierwszym odtworzeniu wyniki
wykonano w Pythonie 3.12.5, NumPy 2.3.4, pandas 2.3.3 i scikit-learn 1.7.2.
Wszystkie 45 dopasowań zakończyło się poprawnie. Rzeczywiste wyniki pilotażu
nie są jeszcze dowodem wykonania pełnego eksperymentu.
