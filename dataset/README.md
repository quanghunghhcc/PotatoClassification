# Potato disease image dataset

## Dataset title

**A multi-view RGB image dataset of four potato varieties with visually assessed scab and dry-rot severity under dual-background imaging conditions**

## Main image archive

**`potato_disease_dataset.zip`**

This archive is the main public image file for the Mendeley Data release. It contains **9,106 RGB JPG images**, standardized to **512 × 512 pixels**, organized into **18 combined variety-condition/severity class folders**. The archive name refers to the dataset file; the internal class-folder names retain the publication-style variety and condition labels.

## Authors

1. **Samiul Islam Saif**  
   Department of Computer Science, American International University-Bangladesh, Kuratoli, Khilkhet, Dhaka 1229, Bangladesh  
   Email: md.samiulislam.aiub@gmail.com  
   ORCID: 0009-0009-7116-7151

2. **Mst. Fahmida Tasnim Saba**  
   Faculty of Agriculture, Hajee Mohammad Danesh Science and Technology University, Dinajpur, Bangladesh  
   Email: fahmidatasnim.hstu@gmail.com  
   ORCID: 0009-0003-7019-0516

3. **M. Shamim Kaiser** — Corresponding author  
   Institute of Information Technology, Jahangirnagar University, Savar, Dhaka 1342, Bangladesh  
   Email: mskaiser@juniv.edu  
   ORCID: 0000-0002-4604-5461

## CRediT author contributions

- **Samiul Islam Saif:** Conceptualization; Data curation; Investigation; Methodology; Software; Visualization; Writing – original draft.
- **Mst. Fahmida Tasnim Saba:** Investigation; Validation; Writing – review & editing.
- **M. Shamim Kaiser:** Supervision; Methodology; Validation; Writing – review & editing.

## Dataset summary

- Main archive: **`potato_disease_dataset.zip`**
- Total images: **9,106**
- Class folders: **18**
- Potato varieties: **4**
  - Rumana
  - BARI Alu-25 (Asterix)
  - Lal Pakri
  - BARI Alu-7 (Diamant)
- Released image format: **RGB JPG**
- Released image size: **512 × 512 pixels**
- Source capture size: approximately **4096 × 3072 pixels**
- Views: **Top, Bottom, Middle, Left, Right**
- Backgrounds: **white paper and concrete floor**
- Lighting: **natural daylight**
- Approximate camera-to-tuber distance: **15–20 cm**
- Devices: **iQOO Neo 11** and **realme Narzo 50**
- Collection location: **New Kafela Cold Storage, Shibganj, Bogura, Bangladesh**
- Collection periods: **November 2025 and July 2026**

Each physical tuber was photographed from five orientations and on both backgrounds, so multiple images may represent the same physical tuber.

## Image standardization for the public release

Source photographs were captured in JPG format at approximately 4096 × 3072 pixels. For the public 512 × 512 release:

1. EXIF orientation was corrected.
2. Images were converted to RGB.
3. Each image was resized with Lanczos resampling while preserving its original aspect ratio.
4. The resized image was centered on a 512 × 512 canvas.
5. Padding color was estimated from four near-corner image pixels after a 64 × 64 reduction.
6. Images were saved as JPEG with quality 95, optimization enabled, and subsampling set to 0.

This procedure avoids geometrically stretching the tuber image.

## Labeling

Variety identity, visible disease condition, and severity category were assigned by visual phenotypic assessment of the tuber surface.

- **Rumana:** Healthy, Scab Mild, Scab Moderate, Scab Severe.
- **BARI Alu-25 (Asterix):** Healthy, DryRot Mild, DryRot Moderate, DryRot Severe, Fully Rotten.
- **Lal Pakri:** Healthy, DryRot Mild, DryRot Moderate, DryRot Severe.
- **BARI Alu-7 (Diamant):** Healthy, DryRot Mild, DryRot Moderate, DryRot Severe, Fully Rotten.

The annotations are **visually assessed phenotypic labels** and were not confirmed by laboratory pathogen testing.

### Fully Rotten operational definition

Tubers were assigned to the Fully Rotten category when they showed advanced decay with widespread darkened necrotic tissue, pronounced tissue collapse or disintegration, and substantial loss of normal tuber structure, making them visually distinct from the Severe category, in which the tuber remained structurally recognizable despite extensive disease symptoms.

## Class distribution

| Class folder | Images |
|---|---:|
| `BARI_Alu_25_Asterix__DryRot_Mild` | 142 |
| `BARI_Alu_25_Asterix__DryRot_Moderate` | 544 |
| `BARI_Alu_25_Asterix__DryRot_Severe` | 1,081 |
| `BARI_Alu_25_Asterix__Fully_Rotten` | 102 |
| `BARI_Alu_25_Asterix__Healthy` | 510 |
| `BARI_Alu_7_Diamant__DryRot_Mild` | 77 |
| `BARI_Alu_7_Diamant__DryRot_Moderate` | 330 |
| `BARI_Alu_7_Diamant__DryRot_Severe` | 885 |
| `BARI_Alu_7_Diamant__Fully_Rotten` | 141 |
| `BARI_Alu_7_Diamant__Healthy` | 514 |
| `Lal_Pakri__DryRot_Mild` | 61 |
| `Lal_Pakri__DryRot_Moderate` | 254 |
| `Lal_Pakri__DryRot_Severe` | 1,292 |
| `Lal_Pakri__Healthy` | 647 |
| `Rumana__Healthy` | 580 |
| `Rumana__Scab_Mild` | 205 |
| `Rumana__Scab_Moderate` | 742 |
| `Rumana__Scab_Severe` | 999 |
| **Total** | **9,106** |

The same class counts are provided in **`potato_dataset_class_counts.csv`**.

## Repository package

The Mendeley Data deposit is intended to contain:

```text
potato_disease_dataset.zip
README.md
potato_dataset_class_counts.csv
resize_manifest.csv
```

### File descriptions

- **`potato_disease_dataset.zip`** — Main archive containing the 9,106 standardized 512 × 512 RGB JPG images in 18 class folders.
- **`README.md`** — Dataset documentation, acquisition information, label definitions, class distribution, processing information, and reuse notes.
- **`potato_dataset_class_counts.csv`** — Verified image count for each of the 18 class folders; each row also identifies the associated archive as `potato_disease_dataset.zip`.
- **`resize_manifest.csv`** — Dataset-level summary of the processing settings used to create the standardized 512 × 512 public release.

## Important reuse note

Because multiple views and backgrounds can correspond to the same physical tuber and stable tuber identifiers were not retained in the filenames, a random image-level machine-learning split should **not** be interpreted as a confirmed tuber-independent split. Researchers should account for this limitation when designing model evaluation protocols.

## License

**CC BY 4.0**

Users may share and adapt the dataset with appropriate attribution under the Creative Commons Attribution 4.0 International license.

## Repository information

Repository: **Mendeley Data**  
Main archive: **`potato_disease_dataset.zip`**  
Version: **1**  

