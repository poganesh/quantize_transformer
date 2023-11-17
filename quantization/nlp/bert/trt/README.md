# BERT QDQ Quantization in ONNX  

## Requirements

* Prepare conda environment
  * Ensure that you have installed AMD-IPU driver successfully.
  * Create a new conda environment based on py39 and install some packages, then activate it:
```
cd quantize_transformer/quantization/nlp/bert/trt
conda env create --name your_conda_env_name -f environment.yml
conda activate your_conda_env_name
```

* The onnx model used in the script is converted from Hugging Face BERT model. https://huggingface.co/transformers/serialization.html#converting-an-onnx-model-using-the-transformers-onnx-package. To dowload the model and save it in onnx format. Run the below command from the conda env created in the previous step.

```
optimum-cli export onnx --model distilbert-base-uncased-distilled-squad distilbert_base_uncased_squad_onnx/
```

* We use [SQuAD](https://rajpurkar.github.io/SQuAD-explorer/) dataset as default dataset which is included in the repo.

## Build BERT App

```
cd trt
# please use powershell to execute this command
./build.ps1
```
When the bert app is built success, the console output would output:
```Build bert success, you could run it now.```

## QDQ Model Generation and Compilation
The **e2e_tensorrt_bert_example.py** is an end-to-end example to do static quantization and compile the model. This file uses the **QDQQuantizer** API from ```onnxruntime.quantization``` for static quantization. 

There are two main steps for the quantization:
1. Calibration is done based on SQuAD dataset to get dynamic range of floating point tensors in the model.
2. Q/DQ nodes with dynamic range (scale and zero-point) are inserted to the model.
3. Once QDQ model generation is done, the qdq_model.onnx will be saved.
4. After Quantization is done, the script compiles the QDQ model based on the target EP.
5. To compile the model for the CPU run the below command:
```
python e2e_tensorrt_bert_example.py --target cpu
```

6. To compile the model for the IPU run the below command:

```python e2e_tensorrt_bert_example.py --target ipu```

To check the output logs and error message please check: https://confluence.amd.com/display/~pooja/Bert+static+quantization+-+tvm+compiler+output+logs


7. To quantize the model using **quantize_static** API from ```onnxruntime.quantization```, run the below command:

 ``` python e2e_bert_example_qs.py --target ipu ```

To check the output logs and error message please check: https://confluence.amd.com/display/~pooja/Bert+static+quantization+-+tvm+compiler+output+logs


