import sys
sys.path.append('/home/berry/gnumpy')
import gnumpy as gp
import numpy as np
import scipy
import scipy.optimize
import deepnet

class NeuralNet(object):
    '''
    Implementation of a Multi-Layer Perception trained by backprop. This class 
    accepts pre-trained networks for use in a deep neural network. Pre-trained 
    nets should consist of a list of objects, where each object has a W and hbias
    variables containing numpy arrays, n_hidden containing the number of 
    hidden units, and hidtype containing a string with the activation type, i.e.
    "sigmoid".


    '''
    def __init__(self, network=None, layer_sizes=None, layer_types=None):
        layers = []
        if network is not None:
            # copy the weights from the given network onto the GPU
            for rbm in network:
                l = Layer(rbm.W, rbm.hbias, rbm.n_hidden, rbm.hidtype)
                layers.append(l)
        else:
            # if no pre-trained network is given, initialize random weights
            assert layer_sizes is not None
            assert layer_types is not None
            assert len(layer_sizes) == len(layer_types)
            for i in range(len(layer_sizes)-1):
                W = 0.1 * np.random.randn(layer_sizes[i], layer_sizes[i+1])
                hbias = -0.4 * np.ones(layer_sizes[i+1])
                l = Layer(W, hbias, layer_sizes[i+1], layer_types[i+1])
                layers.append(l)
        self.network = layers

    def run_through_network(self, data, net=None):
        '''
        Gets the output of the top layer of the network given input data on the 
        bottom.

        args:   
            array data: the input data
            obj net:    the network to use, default is self.network
        returns:
            array hid:  the activation of the top layer 
        '''
        if net is None:
            net = self.network
        hid = data
        for layer in net:
            vis = gp.garray(hid)
            hid = self.get_activation(layer, vis)
            gp.free_reuse_cache()
        return hid

    def get_activation(self, layer, data):
        '''
        Gets the activation of a single layer given input data

        args:
            obj layer:  the layer object 
            array data: the input data
        returns:
            array hid:  the output of the layer
        '''
        hid = np.zeros((data.shape[0], layer.n_hidden))
        breaks = range(0, hid.shape[0], 128)
        breaks.append(hid.shape[0])
        for i in range(len(breaks)-1):
            s = breaks[i]
            e = breaks[i+1]
            act = gp.dot(data[s:e], layer.W) + layer.hbias
            if layer.hidtype == 'sigmoid':
                hid[s:e] = (act.logistic()).as_numpy_array()
            else:
                hid[s:e] = act.as_numpy_array()
        return hid

    def train(self, data, targets, validX=None, validT=None, max_iter=100,
            validErrFunc='classification', targetCost='linSquaredErr'):
        '''
        Trains the network using backprop

        args:
            array data:     the training data
            array targets:  the training labels
            array validX:   the validation data (optional)
            array validT:   the validation labels (optional)
            int max_iter:   the maximum number of backprop iterations
            string validErrFunc: determines which kind of network to train, 
                            i.e. classification or reconstruction
            string targetCost:  determines which cost function to use, i.e.
                            linSquaredErr, crossEntropy, or softMax
                            linSquaredErr works only for gaussian output units
                            softmax works only for exp output units (not implemented)
        '''
        # initialize parameteres
        self.validErrFunc = validErrFunc
        self.targetCost = targetCost
        self.n, self.m = data.shape
        numunits = 0
        for i in range(len(self.network)):
            numunits = numunits + self.network[i].W.shape[1] + \
                    self.network[i].hbias.shape[0]
        self.numunits = numunits
        self.batch_size = 128
        initialfit = 0              # number of iters to train top layer only
        self.weights = np.ones((self.n,))
        
        # For estimating test error
        tindex = np.arange(self.n)
        np.random.shuffle(tindex)
        tinds = tindex[:(np.min([self.batch_size, self.n]))]
        
        # Perform gradient descent
        print "Starting %d iterations of backprop." % max_iter
        if (initialfit>0):  
            # This gets the activation of next to last layer to train top layer 
            transformedX = self.run_through_network(data, self.network[:-1])
        for i in range(max_iter):
            trainerr = self.getError(self.network, data[tinds,:], targets[tinds,:],
                    self.weights[tinds])
            if validX is not None:
                validerr = self.getError(self.network, validX, validT, 
                        np.ones((validX.shape[0],)))
                print "Iteration %3d: TrainErr = %4.3f, ValidErr = %4.3f" % \
                        (i+1, trainerr, validerr)
            else:
                print "Iteration %3d: TrainErr = %4.3f" %(i+1, trainerr)
            # Train the top layer only for initialfit iters
            if (i < initialfit):
                self.doBackprop(transformedX, targets, [self.network[-1]])
            else:
                self.doBackprop(data, targets, self.network)

        # Print the final training error
        trainerr = self.getError(self.network, data[tinds,:], targets[tinds,:],
                self.weights[tinds])
        if validX is not None:
            validerr = self.getError(self.network, validX, validT, 
                    np.ones((validX.shape[0],)))
            print "Final        : TrainErr = %4.3f, ValidErr = %4.3f" % \
                    (trainerr, validerr)
        else:
            print "Final        : TrainErr = %4.3f" %(trainerr)

    def getError(self, network, X, T, weights):
        '''
        Calculates the error for either classification or reconstruction during
        backprop

        args:
            list[obj] network:    the network to use
            X:                    the input data
            T:                    the input targets
            weights:              weights used for backprop

        This function is designed to be called by the train() method
        '''
        err = 0
        result = self.run_through_network(X, network)
        if self.validErrFunc == 'classification':
            for i in range(X.shape[0]):
                ind = np.argmax(result[i,:])
                targ = np.argmax(T[i,:])
                if ind != targ:
                    err = err + weights[i]
        else:
            for i in range(X.shape[0]):
                err = err + np.sqrt(np.sum(np.square(result[i,:]-T[i,:])))*weights[i]
        validerr = err / np.sum(weights)
        return validerr

    def doBackprop(self, data, targets, network):
        '''
        Executes 1 iteration of backprop

        args:
            array data:         the training data
            array targets:      the training targets
            list[obj] network:  the network
        This function is designed to be called by the train() method
        '''
        no_layers = len(network)
        index = np.arange(self.n)
        np.random.shuffle(index)
        for batch in range(0, self.n, self.batch_size):
            if batch + 2*self.batch_size > self.n:
                batchend = self.n
            else:
                batchend = batch + self.batch_size
            # Select current batch
            tmpX = data[index[batch:batchend],:]
            tmpT = targets[index[batch:batchend],:]
            tmpW = self.weights[index[batch:batchend],:]

            # flatten out the weights and store them in v
            v = []
            for i in range(len(network)):
                w = network[i].W.as_numpy_array()
                b = network[i].hbias.as_numpy_array()
                v.extend((w.reshape((w.shape[0]*w.shape[1],))).tolist())
                v.extend(b.tolist())
            v = np.asarray(v)
            
            # Conjugate gradient minimiziation
            #result = scipy.optimize.minimize(self.backprop_gradient, v, 
            #        args=(network, tmpX, tmpT, tmpW),
            #method='CG', jac=True)
            #print "Success: " + str(result.success)
            #if result.success is False:
            #    print result.message
            #    print "Number of evaluations: " + str(result.nfev)
            #    #print result.x.shape
            #v = result.x

            result = self.minimize(self.backprop_gradient, v, args=(network, tmpX, 
                tmpT, tmpW), length=3)
            v = result[0]
            #print result[1], result[2]

            # unflatten v and put new weights back
            ind =0 
            for i in range(len(network)):
                h,w = network[i].W.shape
                network[i].W = gp.garray((v[ind:(ind+h*w)]).reshape((h,w)))
                ind += h*w
                b = len(network[i].hbias)
                network[i].hbias = gp.garray(v[ind:(ind+b)])
                ind += b
        
    def backprop_gradient(self, v, network, X, targets, weights):
        '''
        Calculates the value of the cost function and the gradient for CG 
        optimization.

        args:
            array v:            the 1d vector of weights
            list[obj] network:  the network
            array X:            training data
            array targets:      the training targets
            array weights:      the backprop weights
        returns:
            array cost:         the value of the cost function
            array grad:         the value of the gradient

        This function is called by scipy's minimize function during optimization
        '''
        # initialize variables
        n = X.shape[0]
        numHiddenLayers = len(network)

        # put the v weights back into the network
        ind =0 
        for i in range(numHiddenLayers):
            h,w = network[i].W.shape
            network[i].W = gp.garray((v[ind:(ind+h*w)]).reshape((h,w)))
            ind += h*w
            b = len(network[i].hbias)
            network[i].hbias = gp.garray(v[ind:(ind+b)])
            ind += b

        # Run data through the network, keeping activations of each layer
        acts = [X] # a list of numpy arrays
        hid = X
        for layer in network:
            vis = gp.garray(hid)
            hid = self.get_activation(layer, vis) 
            acts.append(hid)
            gp.free_reuse_cache()

        # store the gradients
        dW = []
        db = []

        # Compute the value of the cost function
        if self.targetCost == 'crossEntropy':
            # see www.stanford.edu/group/pdplab/pdphandbook/handbookch6.html
            cost = (-1.0/n) * np.sum(np.sum(targets * np.log(acts[-1]) + \
                    (1.0 - targets) * np.log(1.0 - acts[-1]), axis=1) * weights)
            Ix = (acts[-1] - targets) / n
        else: #self.targetCost == 'linSquaredErr':
            cost = 0.5 * np.sum(np.sum(np.square(acts[-1] - targets), axis=1) * \
                    weights)
            Ix = (acts[-1] - targets)
        Ix *= np.tile(weights, (1, Ix.shape[1])).reshape((Ix.shape[0],Ix.shape[1]))
        Ix = gp.garray(Ix)

        # Compute the gradients
        for i in range(numHiddenLayers-1,-1,-1):
            # augment activations with ones
            acts[i] = gp.garray(acts[i])
            acts[i] = gp.concatenate((acts[i], gp.ones((n,1))), axis=1)

            # compute delta in next layer
            delta = gp.dot(acts[i].T, Ix)

            # split delta into weights and bias parts
            dW.append(delta[:-1].T)
            try:
                db.append(delta[-1].T)
            except AttributeError:
                # when layer only has 1 unit
                db.append(delta[-1])

            # backpropagate the error
            if i > 0:
                # fix the numpy 1d array issue
                biasr = network[i].hbias.reshape((1,network[i].hbias.shape[0]))
                if network[i-1].hidtype == 'sigmoid':
                    Ix = gp.dot(Ix,gp.concatenate((network[i].W,biasr)).T)\
                            * acts[i] * (1.0 - acts[i])
                elif network[i-1].hidtype == 'gaussian':
                    Ix = gp.dot(Ix,gp.concatentate((network[i].W,biasr)).T)
                Ix = Ix[:,-1]
            gp.free_reuse_cache()
        dW.reverse()
        db.reverse()

        # Convert gradient information
        grad = np.zeros_like(v)
        ind = 0
        for i in range(numHiddenLayers):
            try: 
                grad[ind:(ind+dW[i].size)] = \
                   (dW[i].reshape((dW[i].shape[0]*dW[i].shape[1]))).as_numpy_array()
            except IndexError:
                grad[ind:(ind+dW[i].size)] = dW[i].as_numpy_array()
            ind += dW[i].size
            try:
                grad[ind:(ind+db[i].size)] = db[i].as_numpy_array()
                ind += db[i].size
            except AttributeError:
                # when layer has only 1 node
                grad[ind:(ind+1)] = db[i]
                ind += 1

        return cost, grad  

    def minimize(self, fun, X, args, length):
        '''
        Implements Conjugate Gradient Optimization, which minimizes a continuous
        differentiable multivariate function. Starting point is given by "x", 
        and the function named in "fun" must return a function value and a vector 
        partial derivatives. The Polack-Ribiere flavor of CG is used to compute
        search directions, and a line search using quadratic and cubic polynomial
        approximations and the Wolfe-Powell stopping criteria are used together with
        the slope ratio method ofr guessing initial step sizes.

        args:
            callable fun:   returns the value of the cost function and the partial
                            derivatives
            array X:        the starting point
            args:           a tuple containing the additional arguments to pass to
                            the function
            length:         the number of line searches to perform

        Ported to python from Carl Edward Rasmussen's minimize.m for matlab
        '''
        # constants for line searches. RHO and SIG are the constants in the 
        # Wolfe-Powell conditions
        RHO = 0.01
        SIG = 0.5
        INT = 0.1  #don't reevaluate within 0.1 of the limit of the current bracket
        EXT = 3.0  #extrapolate maximum 3 times the current bracket
        MAX = 20   #max 20 function evaluations per line search
        RATIO = 100 #max allowed slope ratio

        #if len(length) == 2:
        #    red = length[1]
        #    length = length[0]
        #else:
        #    red = 1.0
        red = 1.0
        if length>0:
            S = ['Linesearch']
        else:
            S = ['Function evaluation']

        i = 0 # the run length counter
        ls_failed = 0 # no previous line search has failed
        fX = []
        f1, df1 = fun(X, *args)
        if (length<0):
            i += 1
        s = -df1              #search direction is steepest
        d1 = np.dot(-s.T, s)  #this is the slope
        z1 = red/(1.0-d1)     #initial step

        while i < np.abs(length):
            if (length>0):
                i += 1
            X0 = X.copy()     #make backup copy of current values
            f0 = f1.copy()
            df0 = df1.copy()
            X = X + z1 * s
            f2, df2 = fun(X, *args)
            if (length<0):
                i += 1
            d2 = np.dot(df2.T, s)
            f3, d3, z3 = (f1, d1, -z1)  #initialize point 3 equal to point 1 
            if length>0:
                M = MAX
            else:
                M = min(MAX, -length-i)
            success = 0    #initialize variables
            limit = -1
            while True:
                while ((f2 > f1+z1*RHO*d1) or (d2 > -SIG*d1)) and (M > 0):
                    limit = z1  #tighten the bracket
                    if f2 > f1:
                        z2 = z3 - (0.5*d3*z3*z3)/(d3*z3+f2-f3) #quadratic fit
                    else:
                        A = 6.0*(f2-f3)/z3+3.0*(d2+d3)    #cubic fit
                        B = 3.0*(f3-f2)-z3*(d3+2.0*d2)
                        z2 = (np.sqrt(B*B-A*d2*z3*z3)-B)/A
                    if np.isnan(z2) or np.isinf(z2):
                        z2 = z3/2.0 #if there was a problem, bisect
                    z2 = max(min(z2, INT*z3),(1-INT)*z3) #don't accept too close limits
                    z1 += z2  #update the step
                    X += z2*s
                    f2, df2 = fun(X, *args)
                    M -= 1
                    if (length<0):
                        i += 1
                    d2 = np.dot(df2.T, s)
                    z3 = z3-z2  #z3 is now relative to the locatoin of z2
                if (f2 > f1+z1*RHO*d1) or (d2 > -SIG*d1):
                    break   #this is a failure
                elif (d2 > SIG*d1):
                    success = 1
                    #print "success"
                    break   #success
                elif (M == 0):
                    break   #failure
                A = 6.0*(f2-f3)/z3+3.0*(d2+d3) #make cubic extrapolation
                B = 3.0*(f3-f2)-z3*(d3+2.0*d2)
                z2 = -d2*z3*z3/(B+np.sqrt(B*B-A*d2*z3*z3))
                if (not np.isreal(z2)) or np.isnan(z2) or np.isinf(z2) or (z2<0):
                    if limit < -0.5:
                        z2 = z1 * (EXT-1.0)
                    else:
                        z2 = (limit-z1)/2.0
                elif (limit > -0.5) and (z2+z1 > limit):
                    z2 = (limit-z1)/2.0
                elif (limit < -0.5) and (z2+z1 > z1*EXT):
                    z2 = z1*(EXT-1.0)
                elif z2 < -z3*INT:
                    z2 = -z3*INT
                elif (limit > -0.5) and (z2 < (limit-z1)*(1.0-INT)):
                    z2 = (limit-z1)*(1.0-INT)
                f3, d3, z3 = (f2, d3, -z2)
                z1 += z2
                X += z2*s
                f2, df2 = fun(X, *args)
                M -= 1
                if (length<0):
                    i += 1
                d2 = np.dot(df2.T, s)

            if success == 1:
                f1 = f2
                fX.append(f1)
                #Polack-Ribiere direction
                s = (np.dot(df2.T,df2)-np.dot(df1.T,df2)) / \
                        np.dot(np.dot(df1.T,df1),s) - df2
                tmp = df1
                df1 = df2
                df2 = tmp #swap derivatives
                if d2 > 0:
                    s = -df1
                    d2 = np.dot(-s.T,s)
                z1 = z1 * min(RATIO, d1/(d2-2.2251e-308))
                d1 = d2
                ls_failed = 0
            else:
                X = X0      # restore to point before this line search
                f1 = f0 
                df1 = df0
                if (ls_failed == 1) or (i > np.abs(length)):
                    break   #giving up
                tmp = df1
                df1 = df2
                df2 = tmp
                s = -df1
                z1 = 1.0/(1.0-d1)
                ls_failed = 1

        return X, fX, i



class Layer(object):
    '''
    A hidden layer object

    args:
        array W:    the weight array
        array hbias: the bias weights
        int n_hidden: the number of hidden units
        string hidtype: the activation function "sigmoid" or "gaussian"
    '''
    def __init__(self, W, hbias, n_hidden, hidtype):
        self.W = gp.garray(W)
        self.hbias = gp.garray(hbias)
        self.n_hidden = n_hidden
        self.hidtype = hidtype
   
def demo_xor():
    '''Demonstration of backprop with classic XOR example
    '''
    data = np.array([[0,0],[0,1],[1,0],[1,1]])
    targets = np.array([[0],[1],[1],[0]])
    nn = NeuralNet(layer_sizes=[2,2,1], layer_types=['sigmoid','sigmoid','sigmoid'])
    nn.train(data, targets, max_iter=10, targetCost='crossEntropy')
    print "network test:"
    output = nn.run_through_network(data)
    print output


if __name__ == "__main__":
    demo_xor()

            