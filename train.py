# %% preset


import yaml
import os
import pandas as pd
import numpy as np
import argparse
import json
from typing import Any, Callable, Optional, Tuple
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import time
import copy 
from copy import deepcopy
import torch
import torchvision
import torchvision.transforms as transforms
from torchvision.datasets.vision import VisionDataset
from torch.utils.data import random_split
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from tqdm import tqdm
from torch.optim import lr_scheduler
import util
import ax
from importlib import reload
reload(util)
reload(ax)
import  itertools 
import sys
import logging
reload(util)
from util import increment_path,strip_optimizer
from pathlib import Path

logging.basicConfig(
        format="%(message)s",
        level=logging.INFO)
logger = logging.getLogger(__name__)


# %% functions



def stop(msg='Stop here!'):
    raise Exception(msg)

def test(loader,
    model,
    opt = None,
    # info = None,
    save_dir = Path(''),
    testset = None,
    is_training = False,
    is_savecsv = False,
    criterion = None,
    optimizer = None,
    ):

    

    if is_training:
        device = next(model.parameters()).device  # get model device
        running_loss = 0.0
        running_corrects = 0
        cols = ('','','val_loss','val_acc')
        # cols = ('val_loss','val_acc','','')
    else:
        logger.info("Predicting test dataset...")
        device = torch.device('cuda:0' if torch.cuda.is_available()  else 'cpu')

    val_acc = 0
    pred_list = []
    
    model.eval()
    with torch.no_grad():
        pbar = tqdm(loader,
            # file=sys.stdout,
            leave=True,
            bar_format='{l_bar}{bar:3}{r_bar}{bar:-10b}',
            total=len(loader), mininterval=1,)

        for i,data in enumerate(pbar,0):
            images, labels,_ = data
            images, labels  = images.to(device), labels.to(device)
            outputs = model(images)
            _, preds = torch.max(outputs.data, 1)  # predicted is a batch tensor result
            pred_list += preds.tolist()
            
            if is_training:
                loss = criterion(outputs, labels)
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
                cols_str = ('%10s' * len(cols)) % (cols)
                pbar.set_description(cols_str, refresh=False)
       
        
        if is_training:
            epoch_loss = running_loss / len(loader.dataset)
            epoch_acc = running_corrects.double() / len(loader.dataset)
            s = ('%30.4g' + '%10.4g' * 1) % (epoch_loss,epoch_acc)
            # s = ('%10.4g' + '%10.4g' * 1) % (epoch_loss,epoch_acc)
            logging.info(s)
            val_acc = epoch_acc

  
    # savecsv
    if is_savecsv:
        fn_list = loader.dataset.get_filenames()
        df = pd.DataFrame(columns=['filename','cid'])
        df['filename'] = fn_list
        df['cid'] = pred_list
        unified_fp = str(save_dir/'predictions.csv')
        df.to_csv(unified_fp, encoding='utf-8', index=False)
        logger.info('Done! Check csv: '+ unified_fp )

        # for _emoji only
        csv_fp = str(save_dir/'emoji_submit.csv')
        map_fn2cid = dict(zip(fn_list, pred_list))
        # print(map_fn2cid)
        df = pd.read_csv('/content/02read/sample_submit.csv')
        logger.info('Updaing _emoji df: '+ csv_fp )
        for i in tqdm(df.index):
            # print(i)
            fn = df.iloc[i]['name']
            cls_id =map_fn2cid[fn]
            df.at[i, 'label'] = classes[cls_id]
        df.to_csv(csv_fp, encoding='utf-8', index=False)
        logger.info('done! check: '+ csv_fp )

    return pred_list,val_acc


# rm
# test(testloader,model,testset=raw_test,is_savecsv=1,opt=opt)

# test(testloader,model,testset=raw_test,is_savecsv=1)

def infer(loader,model,classes,batch_index = 0, num = 4 ):
  # test images in loader
  dataiter = iter(loader)
  images, labels,_ = next(itertools.islice(dataiter,batch_index,None))
  images, labels  = images.to(device), labels.to(device)
  images = images[:num]

  # print images
  imshow(torchvision.utils.make_grid(images))

  outputs = model(images)
  _, predicted = torch.max(outputs, 1)
 
  print('Predicted: ', ' '.join('%5s' % classes[predicted[j]]
                              for j in range(len(images))))
  print('GroundTruth: ', ' '.join('%5s' % classes[labels[j]] for j in range(len(images))))

  match_str =' '.join([('v' if (labels[j] == predicted[j] ) else 'x') 
              for j in range(len(images))])
  print('Result: ',match_str)

def show(loader,classes,num=4):
    # preview train 
    # get some random training images
    dataiter = iter(loader)
    images, labels, filenames = dataiter.next()
    images = images[:num]
    # show images
    imshow(torchvision.utils.make_grid(images))
    print(' '.join('%5s' % classes[labels[j]] for j in range(len(images))))
    

def imshow(img):
    # show img
    img = img / 2 + 0.5     # unnormalize
    npimg = img.cpu().numpy()
    plt.imshow(np.transpose(npimg, (1, 2, 0)))
    plt.show()

# %% dataset   
class Emoji(VisionDataset):
    pkl_fp = '/content/_emoji/03save.pkl'
    classes = ('angry', 'disgusted', 'fearful',
            'happy', 'neutral', 'sad', 'surprised')
    cls_names = classes


    def __init__(
            self,
            root: str,
            train: bool = True,
            transform: Optional[Callable] = None,
            target_transform: Optional[Callable] = None,
    ) -> None:

        super(Emoji, self).__init__(root, transform=transform,
                                    target_transform=target_transform)

        self.train = train  # training set or test set

        self.data: Any = []
        self.targets = []

        # now load the pkl
        pkl_fp =  self.pkl_fp
        pkl_data = ax.load_obj(pkl_fp,silent=1)
        loaded_data = pkl_data['train_data'] if train else pkl_data['test_data']

        img_list, fn_list, label_id_list = [], [], []
        if self.train:
            for img_np, fn, labe_id in loaded_data:
                img_list += [img_np]
                fn_list += [fn]
                label_id_list += [labe_id]

        else:
            for img_np, fn in loaded_data:
                img_list += [img_np]
                fn_list += [fn]
                label_id_list += [0]

        img_np_list = np.asarray(img_list)  # convert to np
        img_np_list2 = np.repeat(
            img_np_list[:, :, :, np.newaxis], 3, axis=3)  # expand 1 axis

        # print( img_np_list.shape)
        # print( 'img_np_list2 shape',img_np_list2.shape)

        
        # slice = 100
        # self.data = img_np_list2[:slice]
        # self.filenames = fn_list[:slice]
        # self.targets = label_id_list[:slice]

        self.data = img_np_list2
        self.filenames = fn_list
        self.targets = label_id_list


    def __len__(self) -> int:
        return len(self.data)

    def extra_repr(self) -> str:
        return "Split: {}".format("Train" if self.train is True else "Test")

    def get_filenames(self) -> list:
        return self.filenames

    def __getitem__(self, index: int) -> Tuple[Any, Any, Any]:
        img, target, fn = self.data[index], self.targets[index], self.filenames[index]

        # doing this so that it is consistent with all other datasets
        # to return a PIL Image
        img = Image.fromarray(img)

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target, fn



# %% model  
class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        # self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc1 = nn.Linear(1296, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 7)

    def forward(self, x):
        show_list = []
 
        show_list += [x.shape]
        # print(show_list)
        x = self.pool(F.relu(self.conv1(x)))
        
        show_list += [x.shape]
        x = self.pool(F.relu(self.conv2(x)))
        show_list += [x.shape]
        x = torch.flatten(x, 1) # flatten all dimensions except batch
        show_list += [x.shape]
        x = F.relu(self.fc1(x))
        show_list += [x.shape]
        x = F.relu(self.fc2(x))
        show_list += [x.shape]
        x = self.fc3(x)
        show_list += [x.shape]
        for i,v in enumerate(show_list):
          # print(i,v)
          pass
         
        return x


# %% main



# begin
parser = argparse.ArgumentParser()
parser.add_argument('--weights', type=str, default='', help='initial weights path')
parser.add_argument('--nosave', action='store_true', help='only save final checkpoint')
parser.add_argument('--notest', action='store_true', help='only test final epoch')
parser.add_argument('--evolve', action='store_true', help='evolve hyperparameters')
parser.add_argument('--resume', nargs='?', const=True, default=False, help='resume most recent training')

opt = parser.parse_args(args=[])

# default opt


opt.nosave = False
opt.notest = False
opt.evolve = False
opt.project = 'runs_train'
opt.name = 'exp'
opt.batch = 64
opt.split = 0.8
opt.workers = 2
opt.epochs = 20
opt.save_dir = str(increment_path(Path(opt.project) / opt.name))
# opt.weights = 'runs_train/exp75/weights/last.pt'
opt.resume = 'runs_train/exp76/weights/last.pt'


# Resume opt
if opt.resume:
    ckpt = opt.resume if isinstance(opt.resume, str) else None
    print('ckpt:',ckpt)
    assert os.path.isfile(ckpt), 'ERROR: --resume checkpoint does not exist'
    with open(Path(ckpt).parent.parent / 'opt.yaml') as f:
        opt = argparse.Namespace(**yaml.safe_load(f))  # replace
        opt.weights = ckpt
        print(opt)
    logger.info('Resuming training from %s' % ckpt)

# load opt
logger.info('[+]opt\n' + json.dumps(opt.__dict__, sort_keys=True) )
weights = opt.weights
split_dot = opt.split  
workers = opt.workers
batch_size = opt.batch
epochs = opt.epochs
save_dir = Path(opt.save_dir)
wdir = save_dir / 'weights'

# Directories
wdir.mkdir(parents=True, exist_ok=True)  # make dir
last = wdir / 'last.pt'
best = wdir / 'best.pt'
results_file = save_dir / 'results.txt'


# Save run settings
# with open(save_dir / 'hyp.yaml', 'w') as f:
#     yaml.safe_dump(hyp, f, sort_keys=False)
with open(save_dir / 'opt.yaml', 'w') as f:
    yaml.safe_dump(vars(opt), f, sort_keys=False)


 


# GPU info
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
msg = "\n[+]device \nICH 🚀 v0.1 Using device: {}".format(device) 
#Additional Info when using cuda
if device.type == 'cuda':
    msg = msg + " + "
    msg = msg + torch.cuda.get_device_name(0)
    msg +=  '\nGPU mem_allocated: {}GB, cached: {}GB'.format(
        round(torch.cuda.memory_allocated(0)/1024**3,1),
        round(torch.cuda.memory_reserved(0)/1024**3,1),
    ) 

logger.info(msg)



# Prepare datasets
logger.info('\n[+]load dataset')
transform = transforms.Compose(
    [transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
raw_train = Emoji(root='./data', train=True,
                    transform=transform)
raw_test = Emoji(root='./data', train=False,
                    transform=transform)
classes = raw_train.classes
num_train = int(len(raw_train) * split_dot)
trainset, validset = \
    random_split(raw_train, [num_train, len(raw_train) - num_train],
                    generator=torch.Generator().manual_seed(42))

trainloader = torch.utils.data.DataLoader(trainset, batch_size=batch_size,
                                            shuffle=True, num_workers=workers)
validloader = torch.utils.data.DataLoader(validset, batch_size=batch_size,
                                        shuffle=False, num_workers=workers)
testloader = torch.utils.data.DataLoader(raw_test, batch_size=batch_size,
                                        shuffle=False, num_workers=workers)

dataset_sizes ={'train':len(trainset),"val":len(validset),"test":len(raw_test)}
# info['dataset_size'] = dataset_sizes
logger.info("split_dot:{}, train/test={}/{} \n classes_count: {}, batch_size:{}".format(
    split_dot,len(raw_train),len(raw_test),len(classes),batch_size
))
logger.info("Dataset loaded.")




# Load model
logger.info('\n[+]load model')
pretrained = weights.endswith('.pt')
if pretrained:
    ckpt = torch.load(weights, map_location=device)  # load checkpoint
    model = Net()  # create
    state_dict = ckpt['model'].float().state_dict()  # to FP32
    model.load_state_dict(state_dict, strict=False)  # load
    model.to(device)
    logger.info('Transferred %g/%g items from %s' % (len(state_dict), len(model.state_dict()), weights))  # report
else:
    model = Net()
    model.to(device)

criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9)
logger.info('Model loaded.')



# Resume model
start_epoch, best_acc = 0, 0.0
if pretrained:
    # Optimizer
    if ckpt['optimizer_state_dict'] is not None:
        optimizer.load_state_dict(ckpt['optimizer_state_dict'])
        best_acc = ckpt['best_acc']

    # Results
    if ckpt.get('training_results') is not None:
        results_file.write_text(ckpt['training_results'])  # write results.txt

    # Epochs
    start_epoch = ckpt['epoch'] + 1
    if opt.resume:
        assert start_epoch > 0, '%s training to %g epochs is finished, nothing to resume.' % (weights, epochs)
    
    # Start Training
    logger.info('ckpt epoch '+str(ckpt['epoch']))
    del ckpt, state_dict




# Start Training
logger.info('\n[+]train')
logger.info('Logging results to ' + str(save_dir))
logger.info('Starting training for {} epochs...'.format(epochs))
# clean tqdm 
try:
    tqdm._instances.clear()
except Exception:
    pass
since = time.time()
best_model_wts = copy.deepcopy(model.state_dict())
# scheduler
scheduler = lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.1)
scheduler.last_epoch = start_epoch - 1  # do not move
for epoch in range(start_epoch,epochs):
    logging.info("")
    final_epoch = epoch + 1 == epochs
    # Each epoch has a training and validation phase

    model.train()  # Set model to training mode
    running_loss = 0.0
    running_corrects = 0
    cols = ('Epoch','gpu_mem','tra_loss','train_acc')
    logger.info(('%10s' * len(cols)) % (cols))

    pbar = tqdm(trainloader,
        # file=sys.stdout,
        leave=True,
        bar_format='{l_bar}{bar:3}{r_bar}{bar:-10b}',
        total=len(trainloader), mininterval=1,
    )
    for i,(inputs, labels, _) in  enumerate(pbar,0):
        inputs,labels  = inputs.to(device),labels.to(device)

        # core
        optimizer.zero_grad()
        with torch.set_grad_enabled(True):
            # forward + backward + optimize
            outputs = model(inputs) 
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

        # statistics
        _, preds = torch.max(outputs, 1)
        running_loss += loss.item() * inputs.size(0)
        running_corrects += torch.sum(preds == labels.data)
    
        mloss = running_loss / (i * batch_size + inputs.size(0))
        macc = running_corrects / (i * batch_size + inputs.size(0))
        mem = '%.3gG' % (torch.cuda.memory_reserved() / 1E9 if torch.cuda.is_available() else 0)  # (GB)
        s = ('%10s' * 2 + '%10.4g' * 2) % (
            '%g/%g' % (epoch, epochs - 1), mem ,mloss,macc    )
        pbar.set_description(s, refresh=False)
        # end batch  -----------------
    epoch_loss = running_loss / len(trainloader.dataset)
    epoch_acc = running_corrects.double() / len(trainloader.dataset)
    scheduler.step()
    
    # Validate
    this_best = False
    pred_list,val_acc = test(validloader,
        model,
        is_training = True,
        criterion = criterion,
        optimizer = optimizer,
        )
    if val_acc > best_acc:
        best_acc = val_acc
        best_model = copy.deepcopy(model)
        best_model_wts = copy.deepcopy(model.state_dict())
        this_best = True
        
    # Save
    if (not opt.nosave) or (final_epoch and not opt.evolve):
        ckpt = {
            'epoch': epoch,
            'model': deepcopy(model).half(),
            'optimizer_state_dict': optimizer.state_dict(),
            'loss': epoch_loss,
            'best_acc': best_acc,
        }
        torch.save(ckpt, last)
        if this_best:
            torch.save(ckpt, best)  
        del ckpt
    # end epoch -----------------------------


time_elapsed = time.time() - since
print('{} epochs completed in {:.0f}m {:.0f}s \n'.format(
    epochs - start_epoch , time_elapsed // 60, time_elapsed % 60)) # epoch should + 1?
print('Best val Acc: {:4f}'.format(best_acc))


# Strip optimizers
final = best if best.exists() else last  # final model
for f in last, best:
    if f.exists():
        strip_optimizer(f)  # strip optimizers
        print(f)




# torch.cuda.empty_cache()

# %% test
logger.info('\n[+]test')
model.load_state_dict(best_model_wts)

# will error as sliced
test(testloader,model,testset=raw_test,is_savecsv=1,opt=opt,save_dir = save_dir) 

logger.info('End!')

 

 
#%% exp

util.rm1()

# infer(validloader,model,classes,3)









 

# %% set opt
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--placeholder', type=str,
                        default='blank', help='initial weights path')
    opt = parser.parse_args(args=[])

    print(json.dumps(opt.__dict__, sort_keys=True))

