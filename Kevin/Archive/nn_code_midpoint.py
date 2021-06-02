#predict
from numpy import loadtxt

#import keras functionality for sequential architecture 
#Keras is a free open source Python library for developing and evaluating deep learning models
from keras.models import Sequential
from keras.layers import Dense

#load and format dataset
dataset = loadtxt('/content/AMD_withoutHeaders.csv', delimiter=',')
x = dataset[:,0:12]
y = dataset[:,12]

#model format - models in Keras are defined as a sequence of layers
#we will use a Sequential Model and add layers as needed 
model = Sequential()

#model uses dense class for fully connected layers
#first argument = # of neurons/nodes, 'activation' argument is the activation function 
#relu activation function applied for first 2 layers, 8 args, sigmoid last for binary output
model.add(Dense(12, input_dim=12, activation='relu')) #input layer, where input_dim = number of input features
model.add(Dense(8, activation='relu'))
model.add(Dense(1, activation='sigmoid'))

#compile model using bin_xen for loss fx and adam for stochastic gradient descent fx
#adam is an optimization algorithm that tunes itself and gives good results in a wide range of problems
model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

#fit model trains or 'fits' our model - training occurs over epochs and each epoch is split into batches
#the number of epochs and batch size can be chosen experimentally by trial and error
model.fit(x, y, epochs=180, batch_size=10)

# after training our NN on the dataset, we will make class predictions with the model
predictions = model.predict_classes(x)

#summarize the first X cases - the goal is to achieve the lowest loss (0) and highest accuracy (1) possible
for i in range(len(x)):
  print('%s => predicted %d (expected %d)' % (x[i].tolist(), predictions[i], y[i]))

