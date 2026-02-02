## License & Credits
This project uses code from [c-yn/BioIR](https://github.com/c-yn/BioIR)
Copyright (c) 2024 Yuning Cui
Licensed under the [MIT License](http://opensource.org/license/mit).

# Installation

### Dependencies Installation

PyTorch 1.13.1, Python 3.8.11 기반.

```
cd All_in_One
conda env create -f env.yaml
```

### Dataset Preperation

학습 데이터 경로: ```All_in_One/data/Train/{task_name}``` 디렉터리 (```task_name```: Derain, Dehaze만 사용)
테스트 데이터 경로: ```All_in_One/data/Test/{task_name}```
데모 데이터 경로: ```All_in_One/demo```

```
data
 ┣ Test
 ┃ ┣ dehaze
 ┃ ┃ ┣ gt
 ┃ ┃ ┃ ┣ 1002.jpg
 ┃ ┃ ┃ ┣ 101.jpg
 ┃ ┃ ┃ ┣ _G5I0747.png
 ┃ ┃ ┃ ┣ _G5I0767.png
 ┃ ┃ ┃ ┣ ...
 ┃ ┃ ┗ hazy
 ┃ ┃ ┃ ┣ 1002.jpg
 ┃ ┃ ┃ ┣ 101.jpg
 ┃ ┃ ┃ ┣ _G5I0747.png
 ┃ ┃ ┃ ┣ _G5I0767.png
 ┃ ┃ ┃ ┣ ...
 ┃ ┗ derain
 ┃ ┃ ┣ gt
 ┃ ┃ ┃ ┣ D-211106_O2032R01_021_0002.jpg
 ┃ ┃ ┃ ┣ D-211106_O2032R01_021_0012.jpg
 ┃ ┃ ┃ ┣ kope67-00-00004500-00005050_00004501R.jpg
 ┃ ┃ ┃ ┣ kope67-00-00004500-00005050_00004511R.jpg
 ┃ ┃ ┃ ┣ ...
 ┃ ┃ ┗ rainy
 ┃ ┃ ┃ ┣ D-211106_O2032R01_021_0002.jpg
 ┃ ┃ ┃ ┣ D-211106_O2032R01_021_0012.jpg
 ┃ ┃ ┃ ┣ kope67-00-00004500-00005050_00004501R.jpg
 ┃ ┃ ┃ ┣ kope67-00-00004500-00005050_00004511R.jpg
 ┃ ┃ ┃ ┗ ...
 ┗ Train
 ┃ ┣ Dehaze
 ┃ ┃ ┣ input
 ┃ ┃ ┃ ┣ 1.jpg
 ┃ ┃ ┃ ┣ 10.jpg
 ┃ ┃ ┃ ┣ _G5I0002.png
 ┃ ┃ ┃ ┣ _G5I0021.png
 ┃ ┃ ┃ ┣ img_0001.jpg
 ┃ ┃ ┃ ┣ img_0002.jpg
 ┃ ┃ ┃ ┣ ...
 ┃ ┃ ┗ target
 ┃ ┃ ┃ ┣ 1.jpg
 ┃ ┃ ┃ ┣ 10.jpg
 ┃ ┃ ┃ ┣ _G5I0002.png
 ┃ ┃ ┃ ┣ _G5I0021.png
 ┃ ┃ ┃ ┣ img_0001.jpg
 ┃ ┃ ┃ ┣ img_0002.jpg
 ┃ ┃ ┃ ┣ ...
 ┃ ┗ Derain
 ┃ ┃ ┣ input
 ┃ ┃ ┃ ┣ D-211102_O2032R01_061_0023.jpg
 ┃ ┃ ┃ ┣ D-211102_O2032R01_061_0028.jpg
 ┃ ┃ ┃ ┣ kope67-00-00025200-00025670_00025201R.jpg
 ┃ ┃ ┃ ┣ kope67-00-00025200-00025670_00025211R.jpg
 ┃ ┃ ┃ ┣ ...
 ┃ ┃ ┗ target
 ┃ ┃ ┃ ┣ D-211102_O2032R01_061_0023.jpg
 ┃ ┃ ┃ ┣ D-211102_O2032R01_061_0028.jpg
 ┃ ┃ ┃ ┣ kope67-00-00025200-00025670_00025201R.jpg
 ┃ ┃ ┃ ┣ kope67-00-00025200-00025670_00025211R.jpg
 ┃ ┃ ┃ ┣ ...
```
